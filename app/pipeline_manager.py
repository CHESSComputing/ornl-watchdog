#!/usr/bin/env python3

"""Submit CHAP processing jobs by sending requests to the update daemon."""

from pathlib import Path
import queue as _queue
import threading
import time
import traceback

# When update_raw raises an OSError about a truncated h5 file the
# detector IOC hasn't finished writing yet, retry up to this many times
# with this many seconds between attempts.
_H5_RETRY_LIMIT = 10
_H5_RETRY_DELAY = 5  # seconds

from app import get_logger
from app.chap import setup_raw, setup_strain, update_raw, update_strain
from app.config_writer import create_dataset_configs, update_dataset_configs
from app.state import get_state

logger = get_logger("pipeline_manager")

# Queue for data processing tasks
_task_queue = _queue.Queue()

def _worker():
    """Target function for executing data processing tasks in separate
    thread.
    """
    while True:
        task, args, kwargs = _task_queue.get()
        try:
            task(*args, **kwargs)
        except Exception as exc:
            logger.error(f"Task failed: {exc!r}")
            traceback.print_exc()
        finally:
            _task_queue.task_done()

threading.Thread(target=_worker, daemon=True).start()

def _do_setup(dataset_name, spec_file, map_yaml, data_nxs, nxpath):
    """Write CHAP config files and run the setup pipeline for a new dataset.

    Called by the worker thread.  Runs :func:`create_dataset_configs` to
    write ``map_config.yaml`` and ``pipeline.yaml``, then runs
    :func:`~app.chap.setup_raw` and :func:`~app.chap.setup_strain` to
    create the NeXus container and perform the initial strain-analysis
    setup pass.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    :param spec_file: Absolute path to the SPEC log file for this dataset.
    :type spec_file: str
    :param scan_number: SPEC scan number from the ``newsample`` command.
    :type scan_number: int
    :param map_yaml: Absolute path to ``map_config.yaml``.
    :type map_yaml: str
    :param data_nxs: Absolute path to the NeXus output file.
    :type data_nxs: str
    :param nxpath: NXpath in ``data_nxs`` under which the strain analysis
        group will be written (e.g. ``/dataset1_strain_analysis``).
    :type nxpath: str
    """
    logger.debug(f"create_dataset_configs({dataset_name}, {spec_file})")
    create_dataset_configs(dataset_name, spec_file)
    logger.debug(f"setup_raw({map_yaml}, {data_nxs})")
    setup_raw(map_yaml, data_nxs)
    logger.debug(f"setup_strain({data_nxs}, {nxpath})")
    setup_strain(data_nxs, nxpath)
    logger.info("Done with setup")


def _do_update(dataset_name, scan_numbers, map_yaml, spec_file,
               data_nxs, path_prefix, idx_slice, results_json):
    """Update CHAP config files and run the update pipeline for one scan.

    Called by the worker thread.  Runs :func:`update_dataset_configs` to
    extend the ``scan_numbers`` list in ``map_config.yaml``, then runs
    :func:`~app.chap.update_raw` and :func:`~app.chap.update_strain` to
    write the raw map slice and updated strain-analysis results.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    :param scan_numbers: SPEC scan numbers to process.
    :type scan_numbers: list[int]
    :param map_yaml: Absolute path to ``map_config.yaml``.
    :type map_yaml: str
    :param spec_file: Absolute path to the SPEC log file for this dataset.
    :type spec_file: str
    :param data_nxs: Absolute path to the NeXus file to read from and
        write to.
    :type data_nxs: str
    :param path_prefix: NXpath prefix for the strain-analysis
        ``NexusValuesWriter`` (e.g. ``/dataset1_strain_analysis/``).
    :type path_prefix: str
    :param idx_slice: Write-index slice for ``NexusValuesWriter``, as a
        dict with ``start`` and ``stop`` keys.
    :type idx_slice: dict
    :param results_json: Filename of JSON file for storing simplified
        results for easy access by processes that autonomously drive
        experiments.
    :type results_json: str
    """
    logger.debug(f"update_dataset_configs({dataset_name}, {scan_numbers})")
    update_dataset_configs(dataset_name, scan_numbers)
    for attempt in range(1, _H5_RETRY_LIMIT + 1):
        try:
            logger.debug(f"update_raw({map_yaml}, {spec_file}, {scan_numbers}, {data_nxs})")
            update_raw(map_yaml, spec_file, scan_numbers, data_nxs)
            break
        except OSError as exc:
            if "truncated file" not in str(exc) or attempt == _H5_RETRY_LIMIT:
                raise
            logger.warning(
                f"Detector h5 not ready yet (attempt {attempt}/{_H5_RETRY_LIMIT}), "
                f"retrying in {_H5_RETRY_DELAY}s: {exc}"
            )
            time.sleep(_H5_RETRY_DELAY)
    logger.debug(f"update_strain({data_nxs}, {path_prefix}, {scan_numbers}, {idx_slice}, {results_json})")
    update_strain(data_nxs, path_prefix, scan_numbers, idx_slice, results_json)
    logger.info("Done with update")


def submit_setup(dataset_name, spec_file):
    """Queue the config-write and setup pipeline for a new dataset.

    Derives ``map_yaml``, ``data_nxs``, and ``nxpath`` from
    ``analysis_root`` and ``dataset_name``, then enqueues a single task
    that writes the CHAP config files and runs the setup pipeline.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    :param spec_file: Path to the SPEC file for this dataset.
    :type spec_file: str
    """
    analysis_dir = Path(get_state().analysis_root) / dataset_name
    map_yaml = str(analysis_dir / "map_config.yaml")
    data_nxs = str(analysis_dir / "data.nxs")
    nxpath = f"/{dataset_name}_strain_analysis"
    _task_queue.put((
        _do_setup,
        (dataset_name, spec_file, map_yaml, data_nxs, nxpath),
        {}
    ))


def submit_update(dataset_name, spec_file, scan_numbers, scan_start_idx):
    """Queue config-writes and update pipelines for a batch of new scans.

    Derives ``map_yaml``, ``data_nxs``, and ``path_prefix`` from
    ``analysis_root`` and ``dataset_name``, then enqueues one task per
    scan that updates the CHAP config file and runs the update pipeline.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    :param spec_file: Path to the SPEC file for this dataset.
    :type spec_file: str
    :param scan_numbers: SPEC scan numbers collected during this update.
    :type scan_numbers: list[int]
    :param scan_start_idx: Index in the output map array at which the
        first scan in *scan_numbers* should be written.
    :type scan_start_idx: int
    """
    state = get_state()
    analysis_dir = Path(state.analysis_root) / dataset_name
    map_yaml = str(analysis_dir / "map_config.yaml")
    data_nxs = str(analysis_dir / "data.nxs")
    path_prefix = f"/{dataset_name}_strain_analysis/"
    results_json = str(analysis_dir / "strain_results.json")

    _task_queue.put((
        _do_update,
        (
            dataset_name, scan_numbers, map_yaml, spec_file,
            data_nxs, path_prefix,
            {"start": scan_start_idx,
             "stop": scan_start_idx + len(scan_numbers)},
            results_json,
        ),
        {}
    ))
