#!/usr/bin/env python3

"""Generate configuration files for processing new data with CHAP"""

import logging
from pathlib import Path
import os
import yaml

from app import get_logger
from app.state import get_state

logger = get_logger("config_writer")

def create_dataset_configs(dataset_name):
    """Create CHAP configuration files for a new dataset.

    Creates ``<analysis_root>/<dataset_name>/`` if it does not exist, then
    writes ``map_config.yaml`` and ``pipeline.yaml`` with skeleton
    content derived from application state.  Existing files are left
    untouched.

    :param dataset_name: Name of the dataset; used as the analysis
        subdirectory name and as the map title.
    :type dataset_name: str
    """
    analysis_dir = Path(get_state().analysis_root) / dataset_name
    analysis_dir.mkdir(parents=True, exist_ok=True)

    map_yaml = analysis_dir / "map_config.yaml"
    pipeline_yaml = analysis_dir / "pipeline.yaml"

    if not map_yaml.exists():
        map_config = {
            "title": dataset_name,
            "station": "id1a3",
            "experiment_type": "EDD",
            "spec_scans": [
                {
                    "spec_file": None, # FILL IN THIS FILENAME
                    "scan_numbers": []
                }
            ],
            "independent_dimensions": [
                {
                    "label": "labx",
                    "units": "mm",
                    "data_type": "spec_motor",
                    "name": get_state().labx_motor
                },
                {
                    "label": "labz",
                    "units": "mm",
                    "data_type": "spec_motor",
                    "name": get_state().labz_motor
                }
            ],
            "scalar_data": [] # FILL IN THIS LIST
        }
        with open(map_yaml, "w") as f:
            logger.debug(f"Writing {map_yaml}")
            yaml.dump(map_config, f, sort_keys=False)

    if not pipeline_yaml.exists():
        pipeline = {"config": {}, "pipeline": []} # FILL IN THIS PIPELINE
        with open(pipeline_yaml, "w") as f:
            logger.debug(f"Writing {pipeline_yaml}")
            yaml.dump(pipeline, f, sort_keys=False)

    logger.info(f"Created configs for {dataset_name}")


def update_dataset_configs(dataset_name, scan_numbers):
    """Append new scan numbers to an existing dataset's CHAP configurations.

    Updates ``map_config.yaml`` by extending the ``spec_scans[0].scan_numbers``
    list, and updates ``pipeline.yaml`` by adding a new update-stage entry
    keyed by the current update index from application state.

    :param dataset_name: Name of the dataset to update.
    :type dataset_name: str
    :param scan_numbers: SPEC scan numbers collected during this update.
    :type scan_numbers: list[int]
    """
    analysis_dir = Path(get_state().analysis_root) / dataset_name
    map_yaml = analysis_dir / "map_config.yaml"
    pipeline_yaml = analysis_dir / "pipeline.yaml"

    # Update the map config with new scan numbers
    logger.debug(f"Updating {map_yaml}")
    with open(map_yaml, "r") as f:
        map_config = yaml.safe_load(f)
    map_config["spec_scans"][0]["scan_numbers"].extend(scan_numbers)
    with open(map_yaml, "w") as f:
        yaml.dump(map_config, f, sort_keys=False)
      
    # Update the pipeline config to include a new "update" step for the new scans
    logger.debug(f"Updating {pipeline_yaml}")
    with open(pipeline_yaml, "r") as f:
        pipeline_config = yaml.safe_load(f)
    pipeline_config[
        f"update_{get_state().datasets[dataset_name]['current_update']}"] = [
        # FILL IN THIS LIST
    ]
    with open(pipeline_yaml, "w") as f:
        yaml.dump(pipeline_config, f, sort_keys=False)

    logger.info(f"Updated configs for {dataset_name}")

