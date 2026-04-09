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
    """Return the global :class:`StateConfig` singleton.

    :returns: The current application state, or ``None`` if
        :func:`load_state` has not yet been called.
    :rtype: StateConfig or None
    """
    try:
        global _state
        return _state
    except Exception as exc:
        logger.warning(exc)
        return None


def load_state(statefile):
    """Load application state from a YAML file and store it as the global singleton.

    If *statefile* does not exist, a warning is logged and a default
    :class:`StateConfig` is constructed with no keyword arguments.

    :param statefile: Path to the YAML state file.
    :type statefile: str or pathlib.Path
    :returns: The newly constructed :class:`StateConfig` instance.
    :rtype: StateConfig
    """
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
    """Configuration and runtime state for the SPEC watchdog daemon.

    Constructed from a YAML state file via :func:`load_state`.  After
    construction a :class:`~app.spec_controller.SpecController` is
    automatically created from the SPEC connection parameters by the
    :meth:`validate_spec` model validator.

    :ivar filename: Absolute path to the YAML state file on disk.
    :vartype filename: pathlib.Path
    :ivar spec_host: Hostname or IP address of the SPEC server.
    :vartype spec_host: str
    :ivar spec_port: Port number of the SPEC server.
    :vartype spec_port: int
    :ivar spec_timeout: Timeout for SPEC commands in seconds.
    :vartype spec_timeout: int
    :ivar spec: Live SPEC client controller (populated by validator).
    :vartype spec: app.spec_controller.SpecController or None
    :ivar labx_motor: Mnemonic of the labx motor in SPEC.
    :vartype labx_motor: str
    :ivar labz_motor: Mnemonic of the labz motor in SPEC.
    :vartype labz_motor: str
    :ivar tseries_npts: Number of points in each tseries acquisition.
    :vartype tseries_npts: int
    :ivar tseries_exposure: Exposure time per tseries point in seconds.
    :vartype tseries_exposure: float
    :ivar watch_root: Root directory watched for new datasets and updates.
    :vartype watch_root: pathlib.Path
    :ivar analysis_root: Root directory for CHAP analysis outputs.
    :vartype analysis_root: pathlib.Path
    :ivar calibration_yaml: Path to EDD calibration configuration file.
    :vartype calibration_yaml: pathlib.Path
    :ivar strain_analysis_yaml: Path to strain analysis configuration file.
    :vartype strain_analysis_yaml: pathlib.Path
    :ivar datasets: Mapping of dataset name to per-dataset runtime state.
    :vartype datasets: dict
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
        """Instantiate and attach a :class:`~app.spec_controller.SpecController`.

        Called automatically by Pydantic after the model is constructed.
        Reads SPEC connection and scan parameters from the validated fields.

        :returns: The validated model instance (``self``) with
            :attr:`spec` populated.
        :rtype: StateConfig
        """
        self.spec = SpecController(
            self.spec_host, self.spec_port, self.spec_timeout,
            self.labx_motor, self.labz_motor,
            self.tseries_npts, self.tseries_exposure,
        )
        return self

    def write(self):
        """Persist current state to the YAML file at :attr:`filename`.

        The ``spec`` field is excluded from the serialised output because
        it holds a live client object that cannot be round-tripped through
        YAML.
        """
        with open(self.filename, "w") as f:
            yaml.dump(
                self.model_dump(
                    exclude=["spec"],
                ),
                f,
                sort_keys=False)
        logger.info(f"Wrote state settings to {self.filename}")
