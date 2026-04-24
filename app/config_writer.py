#!/usr/bin/env python3

"""Generate configuration files for processing new data with CHAP"""

import logging
from pathlib import Path
import os
import yaml

from app import get_logger
from app.state import get_state

logger = get_logger("config_writer")

def create_dataset_configs(dataset_name, spec_file, scan_number):
    """Create CHAP configuration files for a new dataset.

    Creates ``<analysis_root>/<dataset_name>/`` if it does not exist, then
    writes ``map_config.yaml`` and ``pipeline.yaml`` with skeleton
    content derived from application state.  Existing files are left
    untouched.

    :param dataset_name: Name of the dataset; used as the analysis
        subdirectory name and as the map title.
    :type dataset_name: str
    """
    _state = get_state()
    analysis_dir = Path(_state.analysis_root) / dataset_name
    analysis_dir.mkdir(parents=True, exist_ok=True)

    map_yaml = analysis_dir / "map_config.yaml"
    pipeline_yaml = analysis_dir / "pipeline.yaml"
    data_nxs = analysis_dir / f"{dataset_name}.nxs"

    if not map_yaml.exists():
        map_config = {
            "validate_data_present": False,
            "title": dataset_name,
            "station": "id1a3",
            "experiment_type": "EDD",
            "sample": {
                "name": dataset_name,
                "description": ""
            },
            "spec_scans": [
                {
                    "spec_file": spec_file,
                    "scan_numbers": [scan_number]
                }
            ],
            "scalar_data": [
                {"label": "SCAN_N", "units": "n/a",
                 "data_type": "smb_par", "name": "SCAN_N"},
                {"label": "rsgap_size", "units": "mm",
                 "data_type": "smb_par", "name": "rsgap_size"},
                {"label": "x_effective", "units": "mm",
                 "data_type": "smb_par", "name": "x_effective"},
                {"label": "z_effective", "units": "mm",
                 "data_type": "smb_par", "name": "z_effective"},
            ],
            "independent_dimensions": [
                {
                    "label": "labx",
                    "units": "mm",
                    "data_type": "smb_par",
                    "name": get_state().labx_motor
                },
                {
                    "label": "laby",
                    "units": "mm",
                    "data_type": "spec_motor",
                    "name": "laby"
                },
                {
                    "label": "labz",
                    "units": "mm",
                    "data_type": "spec_motor",
                    "name": get_state().labz_motor
                },
                {
                    "label": "ometotal",
                    "units": "degrees",
                    "data_type": "smb_par",
                    "name": "ometotal"
                }
            ],
            "presample_intensity": {
                "label": "presample_intensity",
                "units": "counts",
                "data_type": "scan_column",
                "name": "a3ic1"
            },
            "dwell_time_actual": {
                "label": "dwell_time_actual",
                "units": "s",
                "data_type": "scan_column",
                "name": "sec"
            },
            "postsample_intensity": {
                "label": "postsample_intensity",
                "units": "counts",
                "data_type": "scan_column",
                "name": "diode"
            },
            "attrs": {
                "scan_type": 0,
                "config_id": 1,
                "dataset_id": 1
            }
        }
        with open(map_yaml, "w") as f:
            logger.debug(f"Writing {map_yaml}")
            yaml.dump(map_config, f, sort_keys=False)

    if not pipeline_yaml.exists():
        pipeline = {
            "config": {},
            "setup_map": [
                {
                    "common.YAMLReader": {
                        "filename": map_yaml,
                        "schema": "common.models.map.MapConfig",
                    }
                },
                {
                    "common.YAMLReader": {
                        "filename": _state.detector_yaml,
                        "schema": "common.models.map.DetectorConfig",
                    }
                },
                {
                    "common.MapProcessor": {
                        "fill_data": False,
                        "remove_constant_dims": False,
                        "num_proc": 1
                    }
                },
                {
                    "common.NexusWriter": {
                        "filename": data_nxs,
                        "force_overwrite": True,
                    }
                },
            ],
            "setup_strain": [
                {
                    "common.YAMLReader": {
                        "filename": _state.strain_analysis_yaml,
                        "schema": "edd.models.StrainAnalysisConfig",
                    }
                },
                {
                    "common.YAMLReader": {
                        "filename": _state.calibration_yaml,
                        "schema": "edd.models.MCATthCalibrationConfig",
                    }
                },
                {
                    "common.NexusReader": {
                        "filename": data_nxs,
                    }
                },
                {
                    "edd.StrainAnalysisProcessor": {
                        "standalone": True,
                        "setup": True,
                        "update": False,
                        "find_peaks": True,
                        "skip_animation": True,
                        "save_figures": False,
                    }
                },
                {
                    "common.NexusWriter": {
                        "filename": data_nxs,
                        "nxpath": f"/{dataset_name}_strain_analysis",
                        "force_overwrite": True,
                    }
                },
            ]
        }
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

