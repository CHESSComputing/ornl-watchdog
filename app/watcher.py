#!/usr/bin/env python3
"""Watch filesystem for new datasets and updates to existing datasets."""

import logging
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import WATCH_ROOT
from .dataset_manager import initialize_dataset, update_dataset

logger = get_logger("watcher")


class DatasetWatcher(FileSystemEventHandler):

    def on_created(self, event):

        path = Path(event.src_path)

        if path.is_dir():

            dataset = path.name
            initialize_dataset(dataset)

        elif path.suffix == ".txt":

            dataset = path.parent.name
            process_point(dataset, path)