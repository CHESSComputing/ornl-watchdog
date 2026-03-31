#!/usr/bin/env python3

"""Manages datasets"""

import logging

from app import DATASETS, SPEC, get_logger
from app.config_writer import create_dataset_configs, update_dataset_configs
from app.state_registry import write_registry
from app.pipeline_manager import submit_pipeline


logger = get_logger("dataset_manager")


def initialize_dataset(dataset_name):

    if dataset_name in DATASETS:
        logger.warning(f"Dataset already exists: {dataset_name}")
        # Metadata arg for newsample should be 0 to suppress all prompts for manual metadata entry?
        SPEC.enqueue([f"newsample {dataset_name} 0"])
        return

    logger.info(f"Initializing dataset: {dataset_name}")

    def after_newsample():
        create_dataset_configs(dataset_name)
        submit_pipeline(dataset_name, "setup")
        DATASETS[dataset_name] = {
            "current_update": 0,
        }
        write_registry()
 
    SPEC.enqueue(
        # Metadata arg for newsample should be 0 to suppress all prompts for manual metadata entry?
        [f"newsample {dataset_name} 0"],
        callback=after_newsample,
    )


def update_dataset(dataset_name, locations_csv):
    import csv

    logger.info(f"Dataset '{dataset_name}' update detected: {locations_csv}")

    if dataset_name not in DATASETS:
        logger.warning(f"Dataset not found: {dataset_name}")
        return

    # Parse the update file to extract labx, labz coordinates
    new_locations = []
    with open(locations_csv, "r") as f:
        reader = csv.reader(f)
        # FIX will there be a header row?
        for row in reader:
            new_locations.append(row)
    logger.info(f"{locations_csv} contains {len(new_locations)} new locations.")

    # Collect data for each new location and update the dataset configs
    scan_numbers = []
    def after_collect():
        scan_numbers.append(SPEC.scan_n)
    for labx, labz in new_locations:
        SPEC.collect_point(dataset_name, labx, labz, callback=after_collect)

    DATASETS[dataset_name]["current_update"] += 1
    update_dataset_configs(dataset_name, scan_numbers)
    submit_pipeline(dataset_name, f"update_{DATASETS[dataset_name]['current_update']}")
    write_registry()
