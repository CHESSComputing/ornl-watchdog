#!/usr/bin/env python3

"""Submit CHAP processing jobs by sending requests to the update daemon."""

import urllib3
import yaml
from pathlib import Path

import requests

from app import get_logger
from app.state import get_state

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger("pipeline_manager")


def _post(endpoint, body):
    """Send a JSON POST request to the CHAP daemon and log the result.

    :param endpoint: Endpoint path without leading slash
        (``'setup'`` or ``'update'``).
    :type endpoint: str
    :param body: JSON-serialisable request body.
    :type body: dict
    """
    url = f"{get_state().daemon_url.rstrip('/')}/{endpoint}"
    logger.info(f"POST {url}")
    logger.debug(f"POST {url} body: {body}")
    try:
        resp = requests.post(url, json=body, verify=False, timeout=300)
        if resp.ok:
            logger.info(f"POST {url} succeeded: {resp.json()}")
        else:
            logger.error(
                f"POST {url} failed ({resp.status_code}): {resp.text}")
    except Exception as exc:
        logger.error(f"POST {url} raised: {exc}")


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
    _post("setup", {
        "map_config_filename": str(analysis_dir / "map_config.yaml"),
        "map_data_filename": data_nxs,
        "filename": data_nxs,
        "nxpath": f"/{dataset_name}_strain_analysis",
    })


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
        _post("update", {
            "map_config_filename": str(analysis_dir / "map_config.yaml"),
            "spec_file": spec_file,
            "scan_number": scan_number,
            "map_data_filename": data_nxs,
            "filename": data_nxs,
            "path_prefix": path_prefix,
            "idx_slice": {"start": map_idx, "stop": map_idx + 1},
        })
