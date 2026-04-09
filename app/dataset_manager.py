#!/usr/bin/env python3

"""Manages datasets"""

import logging

from app import get_logger
from app.config_writer import create_dataset_configs, update_dataset_configs
from app.pipeline_manager import submit_pipeline
from app.state import get_state


logger = get_logger("dataset_manager")


def initialize_dataset(dataset_name):
    """Initialize a new dataset in SPEC and submit the setup pipeline.

    If *dataset_name* is already registered in application state, a
    ``newsample`` command is still sent (to reset SPEC context) but no
    new configs or pipeline jobs are created.  Otherwise, configs are
    written and the ``"setup"`` pipeline is submitted inside a callback
    that fires after SPEC acknowledges the ``newsample`` command.

    :param dataset_name: Name of the new dataset / sample directory.
    :type dataset_name: str
    """

    if dataset_name in get_state().datasets:
        logger.warning(f"Dataset already exists: {dataset_name}")
        # Metadata arg for newsample should be 0 to suppress all prompts for manual metadata entry?
        get_state().spec.enqueue([f"newsample {dataset_name} 0"])
        return

    logger.info(f"Initializing dataset: {dataset_name}")

    def after_newsample():
        """Callback executed by the SPEC worker after ``newsample`` completes.

        Creates analysis configuration files, submits the setup pipeline,
        registers the dataset in application state, and writes state to disk.
        """
        create_dataset_configs(dataset_name)
        submit_pipeline(dataset_name, "setup")
        get_state().datasets[dataset_name] = {
            "current_update": 0,
        }
        get_state().write()

    get_state().spec.enqueue(
        # Metadata arg for newsample should be 0 to suppress all prompts for manual metadata entry?
        [f"newsample {dataset_name} 0"],
        callback=after_newsample,
    )


def update_dataset(dataset_name, locations_csv):
    """Collect data at new sample locations and update processing configs.

    Parses *locations_csv* for ``(labx, labz)`` coordinate pairs, enqueues
    a :meth:`~app.spec_controller.SpecController.collect_point` command
    sequence for each coordinate, updates the CHAP configuration files with
    the resulting scan numbers, and submits an update pipeline job.

    :param dataset_name: Name of the dataset to update.
    :type dataset_name: str
    :param locations_csv: Path to a CSV file whose rows are
        ``labx, labz`` motor positions.
    :type locations_csv: str or pathlib.Path
    """
    import csv

    logger.info(f"Dataset '{dataset_name}' update detected: {locations_csv}")

    if dataset_name not in get_state().datasets:
        logger.warning(f"Dataset not found: {dataset_name}")
        return

    # Parse the update file to extract labx, labz coordinates
    new_locations = []
    with open(locations_csv, "r") as f:
        reader = csv.reader(f)
        # FIX will there be a header row?
        for row in reader:
            new_locations.append(row)
    logger.info(
        f"{locations_csv} contains {len(new_locations)} new locations."
    )

    # Collect data for each new location and update the dataset configs
    scan_numbers = []
    def after_collect():
        """Callback executed after each ``collect_point`` SPEC sequence.

        Appends the most recently completed SPEC scan number to
        *scan_numbers* so it can be recorded in the map configuration.
        """
        scan_numbers.append(get_state().spec.scan_n)
    for labx, labz in new_locations:
        get_state().spec.collect_point(
            dataset_name, labx, labz, callback=after_collect
        )
    get_state().datasets[dataset_name]["current_update"] += 1
    update_dataset_configs(dataset_name, scan_numbers)
    submit_pipeline(
        dataset_name,
        f"update_{get_state().datasets[dataset_name]['current_update']}"
    )
    get_state().write()
