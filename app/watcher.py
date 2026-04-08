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

    def on_created(self, event):
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
