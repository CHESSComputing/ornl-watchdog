#!/usr/bin/env python3

"""Submit CHAP processing jobs by sending requests to the update daemon."""

import urllib3
import yaml
from pathlib import Path
import queue as _queue
import threading

import requests

from app import get_logger
from app.chap import setup_raw, setup_strain, update_raw, update_strain
from app.state import get_state

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
            logger.error(f'Task failed: {exc}')
        finally:
            _task_queue.task_done()

threading.Thread(target=_worker, daemon=True).start()

def _do_setup(map_config_filename, map_data_filename, filename, nxpath):
    """Run the CHAP code to setup a container for raw & processed EDD
    data.

    :param map_config_filename:
    :type map_config_filename:
    :param map_data_filename:
    :type map_data_filename:
    :param filename:
    :type filename:
    :param nxpath:
    :type nxpath:
    """
    logger.debug(f'setup_raw({map_config_filename}, {map_data_filename})')
    setup_raw(map_config_filename, map_data_filename)
    logger.debug(f'setup_strain({filename}, {nxpath})')
    setup_strain(filename, nxpath)
    logger.info('Done with setup')


def _do_update(map_config_filename, spec_file, scan_number, map_data_filename,
               filename, path_prefix, idx_slice):
    """Run the CHAP code to update an EDD results container with fresh
    raw & processed data.
    """
    logger.debug(
        f'update_raw({map_config_filename}, {spec_file}, '
        f'{scan_number}, {map_data_filename})')
    update_raw(map_config_filename, spec_file, scan_number, map_data_filename)
    logger.debug(
        f'update_strain({filename}, {path_prefix}, '
        f'{scan_number}, {idx_slice})')
    update_strain(filename, path_prefix, scan_number, idx_slice)
    logger.info('Done with update')


def submit_setup(dataset_name):
    """Send a ``/setup`` request to the CHAP daemon for a new dataset.

    Derives all required paths from ``analysis_root`` and
    ``dataset_name``.  The strain analysis NXpath is
    ``/{dataset_name}_strain_analysis``.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    """
    state = get_state()
    analysis_dir = Path(state.analysis_root) / dataset_name
    data_nxs = str(analysis_dir / "data.nxs")
    _task_queue.put((
        _do_setup,
        (
            str(analysis_dir / "map_config.yaml"),
            data_nxs,
            data_nxs,
            f"/{dataset_name}_strain_analysis"
        ),
        {}
    ))


def submit_update(dataset_name, scan_numbers, scan_start_idx):
    """Send one ``/update`` request per scan to the CHAP daemon.

    Reads ``spec_file`` from the dataset's ``map_config.yaml``.
    Sends requests sequentially; each request processes one SPEC scan
    and writes its results at position ``scan_start_idx + i`` in the
    output map array.

    :param dataset_name: Name of the dataset directory under
        ``analysis_root``.
    :type dataset_name: str
    :param scan_numbers: SPEC scan numbers collected during this update.
    :type scan_numbers: list[int]
    :param scan_start_idx: Index in the output map array at which the
        first scan in *scan_numbers* should be written.
    :type scan_start_idx: int
    """
    state = get_state()
    analysis_dir = Path(state.analysis_root) / dataset_name
    data_nxs = str(analysis_dir / "data.nxs")
    path_prefix = f"/{dataset_name}_strain_analysis/"

    with open(analysis_dir / "map_config.yaml") as f:
        map_config = yaml.safe_load(f)
    spec_file = map_config["spec_scans"][0]["spec_file"]

    for i, scan_number in enumerate(scan_numbers):
        map_idx = scan_start_idx + i
        _task_queue.put((
            _do_update,
            (
                str(analysis_dir / "map_config.yaml"),
                spec_file,
                scan_number,
                data_nxs,
                data_nxs,
                path_prefix,
                {"start": map_idx, "stop": map_idx + 1},
            ),
            {}
        ))
