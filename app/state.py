#!/usr/bin/env python3

"""Keep track of the state of the application.  (currently only
dataset update numbers, but could be extended to other things in the
future).
"""

import logging
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional
import yaml

from app import get_logger
from app.spec_controller import SpecController


logger = get_logger("state_registry")


def get_state():
    try:
        global _state
        return _state
    except Exception as exc:
        logger.warning(exc)
        return None


def load_state(statefile):
    logger.info(f"Loading state from {statefile}")
    try:
        with open(statefile, "r") as f:
            state = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"{statefile} not found, starting with default state")
        state = {}
    global _state
    _state = StateConfig(**state)
    logger.info(f"Loaded state: {_state}")
    return _state


class StateConfig(BaseModel):
    """
    Configuration parameters for the SPEC watchdog daemon.

    :ivar spec_host: Hostname or IP address of the SPEC server.
    :vartype spec_host: str
    :ivar spec_port: Port number of the SPEC server.
    :vartype spec_port: int
    :ivar spec_timeout: Timeout for SPEC commands in seconds.
    :vartype spec_timeout: int
    :ivar labx_motor: Name / mnemonic of labx motor in SPEC.
    :vartype labx_motor: str
    :ivar labz_motor: Name / mnemonic of labz motor in SPEC.
    :vartype labz_motor: str
    :ivar tseries_npts: Number of points in each tseries acquisition.
    :vartype tseries_npts: int
    :ivar tseries_exposure: Exposure time for each point in seconds.
    :vartype tseries_exposure: float
    :ivar watch_root: Root directory to watch for new datasets and updates.
    :vartype watch_root: pathlib.Path
    :ivar analysis_root: Root directory for analysis outputs.
    :vartype analysis_root: pathlib.Path
    :ivar calibration_yaml: Absolute path to EDD calibration configuration.
    :vartype calibration_yaml: pathlib.Path
    :ivar strain_analysis_yaml: Absolute path to strain analysis configuration.
    :vartype strain_analysis_yaml: pathlib.Path
    :ivar filename: Absolute path to dataset registry YAML file.
    :vartype filename: pathlib.Path
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    filename: Path

    # SPEC connection
    spec_host: str = Field(default="localhost")
    spec_port: int = Field(default=6511)
    spec_timeout: int = Field(default=30)
    spec: Optional[SpecController] = None

    # Scan settings
    labx_motor: str = Field(default="labx")
    labz_motor: str = Field(default="labz")
    tseries_npts: int = Field(default=10)
    tseries_exposure: float = Field(default=0.1)

    # Automation directory
    watch_root: Path = Field(
        default='/nfs/chess/raw/<cycle>/<station>/<btr>/autonomous_experiment/'
    )
    
    # Analysis settings
    analysis_root: Path = Field(
        default='nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>'
    )
    calibration_yaml: Path = Field(
        default='/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/calibration_config.yaml'
    )
    strain_analysis_yaml: Path = Field(
        default='/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/strain_analysis_config.yaml'
    )

    datasets: dict = {}

    @model_validator(mode="after")
    def validate_spec(self) -> SpecController:
        self.spec = SpecController(
            self.spec_host, self.spec_port, self.spec_timeout,
            self.labx_motor, self.labz_motor,
            self.tseries_npts, self.tseries_exposure,
        )
        return self
    
    def write(self):
        """Write the registry to disk (at self.filename)"""
        with open(self.filename, "w") as f:
            yaml.dump(self.model_dump(), f, sort_keys=False)
        logger.info(f"Wrote state settings to {self.filename}")
