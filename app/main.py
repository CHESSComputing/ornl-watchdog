#!/usr/bin/env python3
"""Main entry point for the application. Sets up the file watcher and
starts the event loop.
"""

import argparse
import logging
import os
import sys
import time
from watchdog.observers import Observer

from app import get_logger
from app.state import load_state, get_state
from app.watcher import DatasetWatcher

logger = get_logger()

def main():
    """Start the watchdog observer and block until interrupted.

    Reads the watch root from application state, schedules a
    :class:`~app.watcher.DatasetWatcher` on that directory (recursively),
    then blocks in a ``while True`` loop until a :exc:`KeyboardInterrupt`
    is received, at which point the observer is stopped and joined.

    :raises FileNotFoundError: If the configured ``watch_root`` directory
        does not exist on the filesystem.
    """
    # Run watchdog daemon
    if not os.path.isdir(get_state().watch_root):
        logger.error(f"Directory {get_state().watch_root} not found")
        raise FileNotFoundError(get_state().watch_root)

    logger.info("Starting watchdog daemon")
    observer = Observer()
    logger.debug(f"observer = {observer}")
    observer.schedule(
        DatasetWatcher(),
        str(get_state().watch_root),
        recursive=True
    )
    logger.info(f"Starting observer")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='''wacthdog daemon for 2026-2 autonomous ORNL EDXRD
        Experiment at 1a3.'''
    )
    parser.add_argument(
        'statefile',
        help='''YAML file containing watchdog program state settings.'''
    )
    args = parser.parse_args(sys.argv[1:])

    load_state(args.statefile)

    main()
