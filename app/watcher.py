#!/usr/bin/env python3
"""Watch filesystem for new datasets and updates to existing datasets."""

import logging
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app import get_logger
from app.dataset_manager import initialize_dataset, update_dataset

logger = get_logger("watcher")


class DatasetWatcher(FileSystemEventHandler):
    """Watchdog event handler that reacts to new files and directories.

    Monitors the configured ``watch_root`` recursively.  When a new
    subdirectory appears it is treated as a new dataset; when a new
    ``.txt`` file appears inside an existing dataset directory it is
    treated as a locations update for that dataset.
    """

    def on_created(self, event):
        """Handle a filesystem creation event.

        Dispatches to :func:`~app.dataset_manager.initialize_dataset` for
        new directories or to :func:`~app.dataset_manager.update_dataset`
        for new ``.txt`` files.  All other file types are silently ignored.

        :param event: Watchdog event object describing the created path.
        :type event: watchdog.events.FileCreatedEvent or
            watchdog.events.DirCreatedEvent
        """
        logger.info(f"New event = {event}")

        path = Path(event.src_path)

        if path.is_dir():
            dataset = path.name
            logger.info(f"Initializing new dataset '{dataset}'")
            initialize_dataset(dataset)

        elif path.suffix == ".txt":
            dataset = path.parent.name
            logger.info(f"New locations for dataset '{dataset}'")
            update_dataset(dataset, path)
