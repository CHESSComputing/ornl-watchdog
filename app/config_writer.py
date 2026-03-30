#!/usr/bin/env python3

"""Generate configuration files for processing new data with CHAP"""

import logging
import yaml

from . import ANALYSIS_ROOT, DATASETS

logger = get_logger("config_writer")

def create_dataset_configs(dataset_name):
    """Create configuration files for processing a new dataset."""
    analysis_dir = ANALYSIS_ROOT / dataset_name
    analysis_dir.mkdir(parents=True, exist_ok=True)

    pipeline_yaml = analysis_dir / "pipeline.yaml"
    map_yaml = analysis_dir / "map_config.yaml"

    if not pipeline_yaml.exists():
        pipeline_yaml.write_text("pipeline: setup\n")

    if not map_yaml.exists():
        map_yaml.write_text("map: empty\n")

    logger.info(f"Created configs for {dataset_name}")


def update_dataset_configs(dataset_name, scan_numbers):
    """Update the processing pipeline for a dataset with new scans."""
    analysis_dir = ANALYSIS_ROOT / dataset_name
    map_yaml = analysis_dir / "map_config.yaml"
    pipeline_yaml = analysis_dir / "pipeline.yaml"

    # Update the map config with new scan numbers
    with open(map_yaml, "a") as f:
        map_config = yaml.load(f, Loader=yaml.CLoader)
        map_config["spec_scans"][0]["scan_numbers"].extend(scan_numbers)
        yaml.dump(map_config, f)
      
    # Update the pipeline config to include a new "update" step for the new scans
    with open(pipeline_yaml, "a") as f:
        pipeline_config = yaml.load(f, Loader=yaml.CLoader)
        pipeline_config[f"update_{DATASETS[dataset_name]['current_update']}"] = [
            # FILL IN THIS LIST
        ]
        yaml.dump(pipeline_config, f)

    logger.info(f"Updated configs for {dataset_name}")

