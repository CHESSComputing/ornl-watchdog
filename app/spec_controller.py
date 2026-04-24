#!/usr/bin/env python3
"""Send commands to the spec server, keep track of queued commands, and handle responses."""

import asyncio
import logging
import queue
import threading
import time

from app import get_logger


logger = get_logger("spec_controller")


class SpecController:
    """Thread-safe client for sending commands to a running SPEC server.

    Commands are queued via :meth:`enqueue` and dispatched one at a time
    by a background worker thread.  Each command sequence may include an
    optional callback that is invoked after the last command in the
    sequence completes successfully.

    :ivar spec_host: Hostname or IP address of the SPEC server.
    :vartype spec_host: str
    :ivar spec_port: TCP port the SPEC server listens on.
    :vartype spec_port: int
    :ivar spec_timeout: Per-command timeout in seconds.
    :vartype spec_timeout: int
    :ivar labx_motor: SPEC mnemonic for the labx motor.
    :vartype labx_motor: str
    :ivar labz_motor: SPEC mnemonic for the labz motor.
    :vartype labz_motor: str
    :ivar tseries_npts: Number of points per ``tseries`` acquisition.
    :vartype tseries_npts: int
    :ivar tseries_exposure: Exposure time per ``tseries`` point in seconds.
    :vartype tseries_exposure: float
    """

    def __init__(
            self,
            spec_host, spec_port, spec_timeout,
            labx_motor, labz_motor,
            tseries_npts, tseries_exposure
    ):
        """Initialise the controller, connect to SPEC, and start the worker thread.

        :param spec_host: Hostname or IP address of the SPEC server.
        :type spec_host: str
        :param spec_port: TCP port the SPEC server listens on.
        :type spec_port: int
        :param spec_timeout: Per-command timeout in seconds.
        :type spec_timeout: int
        :param labx_motor: SPEC mnemonic for the labx motor.
        :type labx_motor: str
        :param labz_motor: SPEC mnemonic for the labz motor.
        :type labz_motor: str
        :param tseries_npts: Number of points per ``tseries`` acquisition.
        :type tseries_npts: int
        :param tseries_exposure: Exposure time per ``tseries`` point in seconds.
        :type tseries_exposure: float
        """
        self.spec_host = spec_host
        self.spec_port = spec_port
        self.spec_timeout = spec_timeout
        self.labx_motor = labx_motor
        self.labz_motor = labz_motor
        self.tseries_npts = tseries_npts
        self.tseries_exposure = tseries_exposure

        self.client = None
        self.async_event_loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self.async_event_loop.run_forever,
            daemon=True
        )
        self._loop_thread.start()
        self._connect()

        self.queue = queue.Queue()
        self.worker = threading.Thread(
            target=self._worker_loop,
            daemon=True
        )
        self._scan_n = self.client.var("SCAN_N")
        self._outfiles = self.client.var("OUTFILES")
        self._datafile = self.client.var("DATAFILE")

        self.worker.start()

    def run_with_timeout(self, coroutine, *coroutine_args, **coroutine_kwargs):
        """Run an async coroutine from a synchronous context with a timeout.

        Schedules *coroutine* on the controller's dedicated event loop via
        :func:`asyncio.run_coroutine_threadsafe` and waits up to
        :attr:`spec_timeout` seconds for a result.

        :param coroutine: Async callable to execute.
        :param coroutine_args: Positional arguments forwarded to *coroutine*.
        :param coroutine_kwargs: Keyword arguments forwarded to *coroutine*.
        :returns: The coroutine's return value, or the raised
            :exc:`Exception` instance if execution failed.
        """
        future = asyncio.run_coroutine_threadsafe(
            coroutine(*coroutine_args, **coroutine_kwargs),
            self.async_event_loop,
        )
        try:
            return future.result(timeout=self.spec_timeout)
        except Exception as e:
            future.cancel()
            return e

    def _connect(self, max_retries=-1, retry_delay=5):
        """Create and connect the ``pyspec`` client, retrying on failure.

        Imports :class:`pyspec.client.Client`, creates an instance pointed
        at :attr:`spec_host`/:attr:`spec_port`, and attempts to enter its
        async context manager (which opens the TCP connection and performs
        the ``HELLO`` handshake).  Success is verified by checking
        ``client._connection.is_connected`` after each attempt.

        If a partial connection is established (TCP open but handshake
        failed), the connection is cleanly exited before the next attempt.

        :param max_retries: Maximum number of connection attempts. If
            less than 0, infinte reties.
        :type max_retries: int
        :param retry_delay: Seconds to wait between attempts.
        :type retry_delay: int or float
        :raises ConnectionError: If all *max_retries* attempts fail.
        """
        from pyspec.client import Client

        logger.info("Initializing pyspec.client.Client")
        self.client = Client(host=self.spec_host, port=self.spec_port)

        attempt = 1
        while attempt <= max_retries or max_retries < 0:
            logger.info(
                f"Connecting to SPEC at {self.spec_host}:{self.spec_port} "
                f"(attempt {attempt}/{max_retries})"
            )
            result = self.run_with_timeout(self.client.__aenter__)

            if not isinstance(result, Exception) and self.client._connection.is_connected:
                logger.info("Connected to SPEC server")
                return

            if isinstance(result, Exception):
                logger.warning(f"Connection attempt {attempt} raised: {result!r}")
            else:
                logger.warning(
                    f"Connection attempt {attempt} failed: "
                    f"is_connected={self.client._connection.is_connected}"
                )

            # Clean up any partial connection state before retrying
            if self.client._connection.is_connected:
                self.run_with_timeout(self.client.__aexit__, None, None, None)

            attempt += 1
            if attempt <= max_retries or max_retries < 0:
                logger.info(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)

        raise ConnectionError(
            f"Failed to connect to SPEC at {self.spec_host}:{self.spec_port} "
            f"after {max_retries} attempt(s)"
        )

    def enqueue(self, command_sequence, callback=None):
        """Add a SPEC command sequence to the processing queue.

        The sequence is consumed by the background worker thread in FIFO
        order.  The optional *callback* is called once after the last
        command in *command_sequence* completes without error.

        :param command_sequence: Ordered list of SPEC command strings.
        :type command_sequence: list[str]
        :param callback: Optional zero-argument callable invoked after the
            sequence completes.
        :type callback: callable or None
        """
        self.queue.put((command_sequence, callback))

    def _send(self, command):
        """Send a single SPEC command, reconnecting first if the connection is lost.

        Checks :attr:`pyspec._connection.connection.Connection.is_connected`
        before each send.  If the connection is down, :meth:`_connect` is
        called to re-establish it before proceeding.

        :param command: SPEC command string to execute.
        :type command: str
        """
        if not self.client._connection.is_connected:
            logger.warning(
                f"SPEC connection lost before sending '{command}', "
                "attempting to reconnect"
            )
            self._connect()

        logger.info(f"Sending SPEC command: {command}")
        result = self.run_with_timeout(self.client.exec, command)
        if isinstance(result, Exception):
            logger.error(f"{command}: {result}")

    def _worker_loop(self):
        """Continuously drain the command queue in a background thread.

        Blocks on :attr:`queue`, dequeues ``(commands, callback)`` tuples,
        sends each command via :meth:`_send`, and then calls *callback* if
        one was supplied.  Exceptions are caught and logged so the worker
        never exits unintentionally.
        """
        while True:
            commands, callback = self.queue.get()
            try:
                for cmd in commands:
                    self._send(cmd)
                if callback:
                    logger.info(
                        f"Running callback after {', '.join([cmd for cmd in commands])}"
                    )
                    callback()
            except Exception as e:
                logger.error(e)
            finally:
                self.queue.task_done()

    def collect_point(self, dataset, labx, labz, callback=None):
        """Enqueue a full data-collection sequence for a single sample point.

        Builds and enqueues the four-command sequence:
        ``newsample``, ``mv labx``, ``mv labz``, ``tseries``.

        :param dataset: Dataset / sample name passed to ``newsample``.
        :type dataset: str
        :param labx: Target labx motor position.
        :type labx: float or str
        :param labz: Target labz motor position.
        :type labz: float or str
        :param callback: Optional zero-argument callable invoked after
            ``tseries`` completes.
        :type callback: callable or None
        """
        commands = [
            f"newsample \"{dataset}\" 0",
            f"mv {self.labx_motor} {labx}",
            f"mv {self.labz_motor} {labz}",
            f"tseries {self.tseries_npts} {self.tseries_exposure}"
        ]
        self.enqueue(commands, callback)

    @property
    def scan_n(self):
        """Current SPEC scan number (``SCAN_N`` variable).

        Fetches the value from SPEC at call time via
        :meth:`run_with_timeout`.  Logs and returns ``None`` on error.

        :returns: Current scan number, or ``None`` if the fetch failed.
        :rtype: int or None
        """
        # return 1
        logger.info("Getting SCAN_N from SPEC")
        result = self.run_with_timeout(self._scan_n.get)
        if isinstance(result, Exception):
            logger.error(result)
        logger.debug(f"Got SCAN_N: {result}")
        return result

    @property
    def outfiles(self):
        logger.info(f"Getting OUTFILES from SPEC")
        result = self.run_with_timeout(self._outfiles.get)
        if isinstance(result, Exception):
            logger.error(result)
        logger.debug(f"Got OUTFILES: {result}")
        return result

    @property
    def datafile(self):
        logger.info(f"Getting DATAFILE from SPEC")
        result = self.run_with_timeout(self._datafile.get)
        if isinstance(result, Exception):
            logger.error(result)
        logger.debug(f"Got DATAFILE: {result}")
        return result

    @property
    def spec_file(self):
        return self.outfiles[(self.datafile, "path")].replace("daq", "raw")
