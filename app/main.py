#!/usr/bin/env python3
"""Main entry point for the application. Sets up the file watcher and
starts the event loop.
"""

import logging
import time
from watchdog.observers import Observer

from . import WATCH_ROOT
from .state_registry import load_registry
from .spec_controller import init_spec_controller
from .watcher import DatasetWatcher

logger = get_logger()

def main():
    logger.info("Starting watchdog daemon")

    observer = Observer()
    observer.schedule(
        DatasetWatcher(),
        str(WATCH_ROOT),
        recursive=True
    )

    observer.start()

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        observer.stop()

    observer.join()


if __name__ == "__main__":
    load_registry()
    init_spec_controller()
    main()