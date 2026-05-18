#!/usr/bin/env python3

"""Manages datasets"""

import csv
import json
import os

from app import get_logger
from app.kuka import position_kuka
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
        )
        get_state().datasets[dataset_name] = {
            "current_update": 0,
            "scan_numbers": [],
        }
        get_state().write()

    after_newsample()


def update_dataset(dataset_name, locations_file):
    """Collect data at new sample locations and update processing configs.

    Parses *locations_file* for new ``(labx, labz)`` coordinate pairs,
    enqueues a
    :meth:`~app.spec_controller.SpecController.collect_point` command
    sequence for each coordinate.  After the last scan completes,
    updates the CHAP configuration files, increments the update
    counter, writes state to disk, and sends update requests to the
    CHAP daemon — all within the final collect callback so that all
    SPEC scan numbers are known before the daemon is contacted.

    :param dataset_name: Name of the dataset to update.
    :type dataset_name: str
    :param locations_file: Path to a CSV/JSON file describing sample
        locations (``labx, labz`` pairs or Kuka joint angles).
    :type locations_file: str or pathlib.Path
    """
    logger.info(f"Dataset '{dataset_name}' update detected: {locations_file}")

    init = False
    if dataset_name not in get_state().datasets:
        logger.warning(f"Dataset not found: {dataset_name}")
        init = True

    # Parse new locations
    new_locations = parse_locations_file(locations_file)
    logger.info(
        f"Parsed {len(new_locations)} new locations from {locations_file}"
    )

    # Collect data for each new location; all work (config updates,
    # state writes, daemon calls) happens inside the final callback so
    # that every SPEC scan number is known before processing begins.
    scan_numbers = []
    n = len(new_locations)

    def make_after_collect(i):
        """Return the per-scan callback for scan index *i*.

        Each callback enqueues the *next* scan rather than pre-loading all
        scans, so any work enqueued inside callback i (e.g. the newsample
        command from initialize_dataset) is guaranteed to complete before
        scan i+1 begins.

        :param i: Zero-based index of this scan within the current
            update batch.
        :type i: int
        :returns: Callback that appends the completed scan number, then
            either enqueues the next scan or, for the last scan, triggers
            config updates and daemon calls.
        :rtype: callable
        """
        def after_collect():
            """Append the completed scan number and enqueue the next
            scan or trigger processing."""
            scan_numbers.append(get_state().spec.scan_n)
            if init and i == 0:
                # Dataset needs to be set up
                initialize_dataset(dataset_name)
            if i == n - 1:
                # All scans for this update are complete.
                # Snapshot both indices before mutating state so that a
                # concurrently-arriving CSV sees the updated values when its
                # own last callback runs (SPEC worker is single-threaded).
                ds = get_state().datasets[dataset_name]
                scan_start_idx = len(ds.get("scan_numbers", []))
                update_i = ds["current_update"]
                ds["current_update"] += 1
                ds.setdefault("scan_numbers", []).extend(scan_numbers)
                submit_update(
                    dataset_name,
                    get_state().spec.spec_file,
                    scan_numbers,
                    scan_start_idx,
                    update_i,
                )
            else:
                # Queue up the NEXT scan & callback
                collect_point(
                    dataset_name, new_locations[i + 1],
                    callback=make_after_collect(i + 1),
                )
            get_state().write()
        return after_collect

    if new_locations:
        collect_point(
            dataset_name, new_locations[0], callback=make_after_collect(0),
        )


def parse_locations_file(locations_file):
    """Parse a locations file and return a list of sample positions.

    Supports two formats determined by file extension:

    * ``.csv`` / ``.txt`` — two-column CSV where each row is
      ``labx, labz`` (floats); rows that cannot be parsed are skipped.
    * ``.json`` — JSON array of Kuka joint-angle positions.

    :param locations_file: Path to the locations file.
    :type locations_file: str or pathlib.Path
    :returns: List of parsed positions (``[labx, labz]`` pairs for CSV,
        raw JSON objects for JSON).
    :rtype: list
    """
    new_locations = []
    _, ext = os.path.splitext(locations_file)
    if ext in (".csv", ".txt"):
        logger.debug(f"Parsing {locations_file} as 2-column CSV")
        with open(locations_file, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) != 2:
                    continue
                logger.debug(f"row: {row}")
                try:
                    _row = [float(x.strip()) for x in row]
                    new_locations.append(_row)
                    logger.info(f"Got location: {_row}")
                except Exception as exc:
                    logger.warning(f"Can't get location: {exc!r}")
    elif ext == ".json":
        logger.debug(
            f"Parsing {locations_file} as Kuka joint angles JSON"
        )
        with open(locations_file, "r") as f:
            new_locations = json.load(f) # OK as is, or more parsing needed?
    else:
        logger.error(f"Locations file extension {ext} not supported")
    return new_locations


def collect_point(dataset, location, callback=None):
    """Enqueue a data-collection sequence for a single sample location.

    Moves the sample positioner (SPEC motors or Kuka robot) to *location*
    and triggers a ``wbseries`` acquisition.  If ``state.kuka_positioner_url``
    is set, Kuka positioning is used and a ``newsample`` command is sent to
    SPEC before the move; otherwise SPEC motor moves are used via
    :meth:`~app.spec_controller.SpecController.collect_point`.

    :param dataset: Dataset / sample name for the SPEC ``newsample`` command.
    :type dataset: str
    :param location: Target position.  For SPEC positioning this must be a
        two-element sequence ``[labx, labz]``; for Kuka positioning the
        format is passed directly to :func:`~app.kuka.position_kuka`.
    :param callback: Optional zero-argument callable invoked after the
        acquisition command completes.
    :type callback: callable or None
    """
    state = get_state()
    if state.kuka_positioner_url is None:
        labx, labz = location
        logger.debug("Using SPEC for sample positioning")
        state.spec.collect_point(dataset, labx, labz, callback=callback)
    else:
        logger.debug("Using Kuka for sample positioning")
        state.spec.enqueue(f"newsample \"{dataset}\" 0")
        position_kuka(location)
        state.spec.enqueue(
            f"wbseries {state.tseries_npts} {state.tseries_exposure}",
            callback=callback,
        )
