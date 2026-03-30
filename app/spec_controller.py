#!/usr/bin/env python3
"""Send commands to the spec server, keep track of queued commands, and handle responses."""

import asyncio
import logging

from . import SPEC_HOST, SPEC_PORT

logger = get_logger("spec_controller")

def init_spec_controller():
    logger.info("Initializing SpecController")
    global SPEC
    SPEC = SpecController()

class SpecController:

    def __init__(self, spec_host, spec_port):
        self.spec_host = spec_host
        self.spec_port = spec_port
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

    def _connect(self):
        from pyspec.client import Client

        logger.info("Initializing pyspec Client")
        self.client = Client(host=self.spec_host, port=self.spec_port)
        await self.client.__aenter__()
        logger.info("pyspec Client connected")

    def enqueue(self, command_sequence, callback=None):
        """
        Queue a SPEC command sequence.

        command_sequence: list[str]
        callback: optional function executed after completion
        """
        self.queue.put((command_sequence, callback))

    def _send(self, command):
        logger.info(f"Sending SPEC command: {command}")
        with asyncio.Timeout(COMMAND_TIMEOUT):
            future = asyncio.run_coroutine_threadsafe(
                self.client.exec(cmd),
                self.async_event_loop,
            )
            try:
                result = future.result(timeout=10)
                logger.info("client.exec succeeded", extra={"cmd": cmd})
            except asyncio.TimeoutError:
                logger.error("client.exec timed out", extra={"cmd": cmd})
            except Exception as e:
                logger.exception("client.exec failed", extra={"cmd": cmd})

    def _worker_loop(self):
        while True:
            commands, callback = self.queue.get()
            try:
                for cmd in commands:
                    self._send(cmd)
                if callback:
                    self.logger("Running callback after '{cmd}")''
                    callback()
            except Exception as e:
                logger.error("SPEC command failure:", exc_info=True)
            finally:
                self.queue.task_done()

    def collect_point(self, dataset, labx, labz, callback=None):
        commands = [
            f"newsample {dataset}",
            f"mv LABX_MOTOR {labx}",
            f"mv LABZ_MOTOR {labz}",
            f"tseries {TSERIES_NPTS} {TSERIES_EXPOSURE}",
        ]
        self.enqueue(commands, callback)

    @property
    def scan_n():
        return await self._scan_n.get()