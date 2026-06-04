#!/usr/bin/env python3

"""Keep track of the state of the application.  (currently only
dataset update numbers, but could be extended to other things in the
future).
"""

from functools import cached_property
import logging
from pathlib import Path
from typing import Annotated, Optional

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    PlainSerializer
)
import yaml

from app import get_logger
from app.spec_controller import SpecController, TestSpecController


logger = get_logger("state")


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


def tolist(arr):
    """Serialier func for StateConfig.kuka_transform_matrix"""
    if isinstance(arr, np.ndarray):
        return arr.tolist()
    return arr

class StateConfig(BaseModel):
    """Configuration and runtime state for the SPEC watchdog daemon.

    Constructed from a YAML state file via :func:`load_state`.  After
    construction a SPEC controller is automatically attached by the
    :meth:`validate_spec` model validator — a
    :class:`~app.spec_controller.SpecController` when :attr:`spec_test` is
    ``False`` (the default), or a
    :class:`~app.spec_controller.TestSpecController` when it is ``True``.

    :ivar filename: Absolute path to the YAML state file on disk.
    :vartype filename: pathlib.Path
    :ivar spec_host: Hostname or IP address of the SPEC server.
    :vartype spec_host: str
    :ivar spec_port: Port number of the SPEC server.
    :vartype spec_port: int
    :ivar spec_timeout: Timeout for SPEC commands in seconds.
    :vartype spec_timeout: int
    :ivar spec_test: When ``True``, use
        :class:`~app.spec_controller.TestSpecController` instead of
        connecting to a real SPEC server.
    :vartype spec_test: bool
    :ivar spec: Live SPEC controller (populated by validator).
    :vartype spec: app.spec_controller.SpecController or
        app.spec_controller.TestSpecController or None
    :ivar kuka_positioner_url: Base URL of the Kuka positioner HTTP server,
        or ``None`` to use SPEC motor moves for sample positioning.
    :vartype kuka_positioner_url: str or None
    :ivar kuka_sample_to_flange: 4x4 transformation matrix for
        converting position matrices in sample coordinates to robot
        flange coordinates, defaults to ``None``.
    :vartype kuka_sample_to_flange: nump.ndarray, optional
    :ivar kuka_nominal_lab_to_sample: 4x4 transformation matrix for
        converting position matrices in lab coordinates to sample
        coordinates, defaults to ``None``.
    :vartype kuka_nominal_lab_to_sample: nump.ndarray, optional
    :ivar labx_motor: Mnemonic of the labx motor in SPEC.
    :vartype labx_motor: str
    :ivar laby_motor: Only used when the kuka robot is being used for
        sample positioning. Mnemonic of the laby motor in
        SPEC. Defaults to ``None``
    :vartype laby_motor: str, optional
    :ivar labz_motor: Mnemonic of the labz motor in SPEC.
    :vartype labz_motor: str
    :ivar scan_command: SPEC scan command to run at every point.
    :vartype scan_command: str
    :ivar watch_root: Root directory watched for new datasets and updates.
    :vartype watch_root: pathlib.Path
    :ivar analysis_root: Root directory for CHAP analysis outputs.
    :vartype analysis_root: pathlib.Path
    :ivar detectors_yaml: Path to EDD detector configuration file.
    :vartype detectors_yaml: pathlib.Path
    :ivar calibration_yaml: Path to EDD calibration configuration file.
    :vartype calibration_yaml: pathlib.Path
    :ivar strain_analysis_yaml: Path to strain analysis configuration file.
    :vartype strain_analysis_yaml: pathlib.Path
    :ivar analysis_test: When ``True``, enqueue :func:`_test_setup` /
        :func:`_test_update` instead of the real CHAP pipelines.
    :vartype analysis_test: bool
    :ivar nsdf_root: Root directory for NeXus files to be visualized
        with NSDF (ORNL only). Defaults to None
    :vartype nsdf_root: pathlib.Path, optional
    :ivar datasets: Mapping of dataset name to per-dataset runtime state.
    :vartype datasets: dict
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    filename: Path

    # SPEC connection
    spec_host: str = Field(default="localhost")
    spec_port: int = Field(default=6511)
    spec_timeout: int = Field(default=30)
    spec_test: bool = Field(default=False)
    spec: Optional[SpecController] = None

    # Sample positioner settings
    labx_motor: str = Field(default="labx")
    laby_motor: Optional[str] = Field(default=None)
    labz_motor: str = Field(default="labz")

    # Kuka settings
    kuka_positioner_url: Optional[str] = None
    kuka_sample_to_flange: Optional[
        Annotated[np.array, PlainSerializer(tolist)]] = None
    kuka_nominal_lab_to_sample: Optional[
        Annotated[np.array, PlainSerializer(tolist)]] = None

    # Scan settings
    scan_command: str = Field(default="wbtseries 1 10")

    # Automation directory
    watch_root: Path = Field(
        default='/nfs/chess/raw/<cycle>/<station>/<btr>/autonomous_experiment/'
    )
    # Analysis settings
    analysis_root: Path = Field(
        default='nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>'
    )
    detectors_yaml: Path = Field(
        default='/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/xps23_config.yaml'
    )
    calibration_yaml: Path = Field(
        default='/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/calibration_config.yaml'
    )
    strain_analysis_yaml: Path = Field(
        default='/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/strain_analysis_config.yaml'
    )

    # Analysis test mode
    analysis_test: bool = Field(default=False)

    # NSDF directory
    nsdf_root: Optional[Path] = None # default: '/nfs/chess/nsdf01/nsdf/workflow/'

    datasets: dict = {}

    @cached_property
    def kuka_flange_to_sample(self):
        return np.linalg.inv(self.kuka_sample_to_flange)

    @model_validator(mode="after")
    def validate_spec(self) -> "StateConfig":
        """Instantiate and attach a SPEC controller.

        Uses :class:`~app.spec_controller.TestSpecController` when
        :attr:`spec_test` is ``True``, otherwise
        :class:`~app.spec_controller.SpecController`.

        Called automatically by Pydantic after the model is constructed.
        Reads SPEC connection and scan parameters from the validated fields.

        :returns: The validated model instance (``self``) with
            :attr:`spec` populated.
        :rtype: StateConfig
        """
        cls = TestSpecController if self.spec_test else SpecController
        self.spec = cls(
            self.spec_host, self.spec_port, self.spec_timeout,
            self.labx_motor, self.labz_motor,
            self.scan_command,
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
                    mode='json',
                ),
                f,
                sort_keys=False)
        logger.info(f"Wrote state settings to {self.filename}")
