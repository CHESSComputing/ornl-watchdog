#!/usr/bin/env python3
"""Send commands to the spec server, keep track of queued commands, and handle responses."""

import asyncio
import logging
import queue
import threading

from app import get_logger


logger = get_logger("spec_controller")


class SpecController:

    def __init__(
            self,
            spec_host, spec_port, spec_timeout,
            labx_motor, labz_motor,
            tseries_npts, tseries_exposure
    ):
        self.spec_host = spec_host
        self.spec_port = spec_port
        self.spec_timeout = spec_timeout
        self.labx_motor = labx_motor
        self.labz_motor = labz_motor
        self.tseries_npts = tseries_npts
        self.tseries_exposure = tseries_exposure

        self.client = None
        self.async_event_loop = asyncio.new_event_loop()
        self._connect()

        self.queue = queue.Queue()
        self.worker = threading.Thread(
            target=self._worker_loop,
            daemon=True
        )
        self._scan_n = self.client.var("SCAN_N")

        self.worker.start()

    def run_with_timeout(self, coroutine, *coroutine_args, **coroutine_kwargs):
        # return
        async def run():
            async with asyncio.Timeout(self.spec_timeout):
                future = asyncio.run_coroutine_threadsafe(
                    coroutine(*coroutine_args, **coroutine_kwargs),
                    self.async_event_loop,
                )
                try:
                    result = future.result(timeout=self.spec_timeout)
                    return result
                except Exception as e:
                    return e
        return asyncio.run(run())

    def _connect(self):
        from pyspec.client import Client

        logger.info("Initializing pyspec.client.Client")
        self.client = Client(host=self.spec_host, port=self.spec_port)
        self.run_with_timeout(self.client.__aenter__)
        logger.info("pyspec.client.Client connected")

    def enqueue(self, command_sequence, callback=None):
        """
        Queue a SPEC command sequence.

        command_sequence: list[str]
        callback: optional function executed after completion
        """
        self.queue.put((command_sequence, callback))

    def _send(self, command):
        logger.info(f"Sending SPEC command: {command}")
        result = self.run_with_timeout(self.client.exec, command)
        if isinstance(result, Exception):
            logger.exception("Failed", extra={"command": command, "exc": result})

    def _worker_loop(self):
        while True:
            commands, callback = self.queue.get()
            try:
                for cmd in commands:
                    self._send(cmd)
                if callback:
                    logger.info(f"Running callback after '{cmd}'")
                    callback()
            except Exception as e:
                logger.error("SPEC command failure:", exc_info=True)
            finally:
                self.queue.task_done()

    def collect_point(self, dataset, labx, labz, callback=None):
        commands = [
            f"newsample {dataset}",
            f"mv {self.labx_motor} {labx}",
            f"mv {self.labz_motor} {labz}",
            f"tseries {self.tseries_npts} {self.tseries_exposure}"
        ]
        self.enqueue(commands, callback)

    @property
    def scan_n(self):
        # return 1
        logger.info("Getting SCAN_N from SPEC")
        result = self.run_with_timeout(self._scan_n.get)
        if isinstance(result, Exception):
            logger.exception("Failed", extra={"exc": result})

