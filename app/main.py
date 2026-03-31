#!/usr/bin/env python3
"""Main entry point for the application. Sets up the file watcher and
starts the event loop.
"""

import logging
import os
import time
from watchdog.observers import Observer

from app import WATCH_ROOT, get_logger
from app.watcher import DatasetWatcher

logger = get_logger()

def main():
    if not os.path.isdir(WATCH_ROOT):
        logger.error(f"Directory {WATCH_ROOT} not found")
        raise FileNotFoundError(WATCH_ROOT)

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
    main()
