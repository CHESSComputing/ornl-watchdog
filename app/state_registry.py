#!/usr/bin/env python3

"""Keep track of the state of the application.
(currently only dataset update numbers, but could be extended to other things in the future)
"""

import logging
import yaml

from app import REGISTRY_YAML, get_logger

logger = get_logger("state_registry")

class StateRegistry:
    def __init__(self, filename=None):
        self.filename = filename

        self.datasets = {}

    def read(self):
        """Read the registry from disk."""
        logger.info(f"Loading registry from {REGISTRY_YAML}")
        try:
            with open(self.filename, "r") as f:
                self.registry = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("registry not found, starting with empty registry")
            self.registry = {}

    def write(self):
        """Write the registry to disk."""
        with open(self.filename, "w") as f:
            yaml.dump(self.registry, f, sort_keys=False)
        logger.info(f"Wrote registry to {REGISTRY_YAML}")

def load_registry():
    """Read the registry from disk."""
    logger.info(f"Loading registry from {REGISTRY_YAML}")
    try:
        with open(REGISTRY_YAML, "r") as f:
            registry = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("registry not found, starting with empty registry")
        registry = {}
    return registry

def write_registry():
    """Write the registry to disk."""
    from app import DATASETS
    with open(REGISTRY_YAML, "w") as f:
        yaml.dump(DATASETS, f, sort_keys=False)
    logger.info(f"Wrote registry to {REGISTRY_YAML}")
