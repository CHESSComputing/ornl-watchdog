#!/usr/bin/env python3

"""Manages datasets"""

import csv
import yaml
from pathlib import Path

from app import get_logger
from app.pipeline_manager import submit_setup, submit_update
from app.state import get_state


logger = get_logger("dataset_manager")


def initialize_dataset(dataset_name):
    """Initialize a new dataset in SPEC and submit the setup pipeline.

    If *dataset_name* is already registered in application state, a
    ``newsample`` command is still sent (to reset SPEC context) but no
    new configs or pipeline jobs are created.  Otherwise, configs are
    written and the setup pipeline is submitted via the CHAP daemon
    inside a callback that fires after SPEC acknowledges the
    ``newsample`` command.

    :param dataset_name: Name of the new dataset / sample directory.
    :type dataset_name: str
    """

    if dataset_name in get_state().datasets:
        logger.warning(f"Dataset already exists: {dataset_name}")
        get_state().spec.enqueue([f"newsample \"{dataset_name}\" 0"])
        return

    logger.info(f"Initializing dataset: {dataset_name}")

    def after_newsample():
        """Callback executed by the SPEC worker after ``newsample`` completes.

        Queues config creation and the setup pipeline, registers the
        dataset in application state, and writes state to disk.
        """
        submit_setup(
            dataset_name,
            get_state().spec.spec_file,
            get_state().spec.scan_n,
        )
        get_state().datasets[dataset_name] = {
            "current_update": 0,
        }
        get_state().write()

    get_state().spec.enqueue(
        [f"newsample \"{dataset_name}\" 0"],
        callback=after_newsample,
    )


def update_dataset(dataset_name, locations_csv):
    """Collect data at new sample locations and update processing configs.

    Parses *locations_csv* for ``(labx, labz)`` coordinate pairs, enqueues
    a :meth:`~app.spec_controller.SpecController.collect_point` command
    sequence for each coordinate.  After the last scan completes,
    updates the CHAP configuration files, increments the update counter,
    writes state to disk, and sends update requests to the CHAP daemon —
    all within the final collect callback so that all SPEC scan numbers
    are known before the daemon is contacted.

    :param dataset_name: Name of the dataset to update.
    :type dataset_name: str
    :param locations_csv: Path to a CSV file whose rows are
        ``labx, labz`` motor positions.
    :type locations_csv: str or pathlib.Path
    """
    logger.info(f"Dataset '{dataset_name}' update detected: {locations_csv}")

    if dataset_name not in get_state().datasets:
        logger.warning(f"Dataset not found: {dataset_name}")
        return

    # Parse new locations
    new_locations = []
    with open(locations_csv, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) != 2:
                continue
            logger.debug(f"row: {row}")
            try:
                _row = [int(x.strip()) for x in row]
                new_locations.append(_row)
                logger.info(f"Got location: {_row}")
            except Exception as exc:
                logger.warning(f"Can't get location: {exc!r}")
    logger.info(
        f"{locations_csv} contains {len(new_locations)} new locations."
    )

    # Record the number of scans already in the map before this update
    # so we know which map-array indices the new scans correspond to.
    analysis_dir = Path(get_state().analysis_root) / dataset_name
    with open(analysis_dir / "map_config.yaml") as f:
        existing_map_config = yaml.safe_load(f)
    scan_start_idx = len(existing_map_config["spec_scans"][0]["scan_numbers"])

    # Collect data for each new location; all work (config updates,
    # state writes, daemon calls) happens inside the final callback so
    # that every SPEC scan number is known before processing begins.
    scan_numbers = []
    n = len(new_locations)

    def make_after_collect(i):
        """Return the per-scan callback for scan index *i*.

        :param i: Zero-based index of this scan within the current
            update batch.
        :type i: int
        :returns: Callback that appends the completed scan number and,
            for the last scan, triggers config updates and daemon calls.
        :rtype: callable
        """
        def after_collect():
            scan_numbers.append(get_state().spec.scan_n)
            if True: #i == n - 1:
                # All scans for this update are complete.
                get_state().datasets[dataset_name]["current_update"] += 1
                submit_update(
                    dataset_name,
                    get_state().spec.spec_file,
                    [scan_numbers[-1]],
                    scan_start_idx,
                )
                get_state().write()
        return after_collect

    for i, (labx, labz) in enumerate(new_locations):
        get_state().spec.collect_point(
            dataset_name, labx, labz, callback=make_after_collect(i)
        )
