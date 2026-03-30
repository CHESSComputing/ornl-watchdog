#!/usr/bin/env python3

"""Keep track of the state of the application.
(currently only dataset update numbers, but could be extended to other things in the future)
"""

import logging
import yaml

from . import DATASET_REGISTRY

logger = get_logger("state_registry")

def load_registry():
    """Read the dataset registry from disk."""
    logging.info(f"Loading dataset registry from {REGISTRY_FILE}")
    try:
        with open(REGISTRY_FILE, "r") as f:
            registry = yaml.load(f, Loader=yaml.CLoader)
            DATASETS = registry
    except FileNotFoundError:
        logging.warning("Dataset registry not found, starting with empty registry")
        DATASETS = {}

def write_registry():
    """Write the dataset registry to disk."""
    with open(REGISTRY_FILE, "w") as f:
        yaml.dump(DATASETS, f)
    logging.info(f"Wrote dataset registry to {REGISTRY_FILE}")
