#!/usr/bin/env python3

"""Shortcuts for running live CHAP.edd data processing
with significantly less overhead than using the CHAP CLI.
"""

import os
from copy import deepcopy

from CHAP.common.map_utils import MapSliceProcessor
from CHAP.common.processor import MapProcessor
from CHAP.common.reader import NexusReader, YAMLReader
from CHAP.common.writer import NexusValuesWriter, NexusWriter
from CHAP.edd.reader import SliceNXdataReader
from CHAP.edd.processor import StrainAnalysisProcessor
from CHAP.common.models import IndexSliceConfig
from CHAP.pipeline import PipelineData
from CHAP.models import RunConfig

from app import get_logger
from app.state import get_state

logger = get_logger(__name__)


def _read_yaml(filename, schema):
    """Read a YAML file and return a tagged ``PipelineData`` object.

    Resolves ``filename`` against ``RUN_CFG.inputdir`` and reads the
    YAML contents into a ``PipelineData`` dict tagged with ``schema``.
    Intended to be called once at startup to cache static
    configurations.

    :param filename: YAML filename (relative to ``RUN_CFG.inputdir``).
    :type filename: str
    :param schema: Fully qualified CHAP schema name used to tag the
        returned ``PipelineData`` (e.g.
        ``'edd.models.StrainAnalysisConfig'``).
    :type schema: str
    :return: Pipeline data item carrying the parsed YAML contents.
    :rtype: CHAP.pipeline.PipelineData
    """
    logger.info(f"Reading {filename}")
    r = YAMLReader(filename=str(filename), schema=schema)
    return PipelineData(
        name='YAMLReader', data=r.read(), schema=schema
    )


def load_data():
    _state = get_state()
    if _state is not None:
        global _STRAIN_CFG, _TTH_CFG, _DETECTORS_CONFIG
        _STRAIN_CFG = _read_yaml(
            _state.strain_analysis_yaml,
            'edd.models.StrainAnalysisConfig'
        )
        _TTH_CFG = _read_yaml(
            _state.calibration_yaml,
            'edd.models.MCATthCalibrationConfig'
        )
        _DETECTORS_CONFIG = _read_yaml(
            _state.detectors_yaml,
            'common.models.map.DetectorConfig'
        )

def _strain_cfg():
    try:
        global _STRAIN_CFG
        return _STRAIN_CFG
    except Exception as exc:
        logger.warning(exc)
        return None

def _tth_cfg():
    try:
        global _TTH_CFG
        return _TTH_CFG
    except Exception as exc:
        logger.warning(exc)
        return None

def _detectors_cfg():
    try:
        global _DETECTORS_CFG
        return _DETECTORS_CFG
    except Exception as exc:
        logger.warning(exc)
        return None

def _init_data():
    return [_strain_cfg(), _tth_cfg()]

# Fixed args for the processor and writer (everything except the
# per-run fields)
_READER_ARGS = dict(
    filename='data.nxs',
    scan_number=0,
)
_PROC_ARGS = dict(
    standalone=True, setup=False, update=True,
    find_peaks=True, skip_animation=True, save_figures=False,
)
_SETUP_STRAIN_PROC_ARGS = dict(
    standalone=True, setup=True, update=False,
    find_peaks=True, skip_animation=True, save_figures=False,
)
_WRITER_ARGS = dict(
    filename='data.nxs',
    path_prefix='/testflight-0212-b_dataset1_strain_analysis/',
    resize_axis=0, force_overwrite=True,
)

# Module-level singletons; filenames are mutated per call to avoid
# re-running pydantic validation (which resolves paths against inputdir
# / outputdir once at construction time).
_READER = SliceNXdataReader(**_READER_ARGS)
_WRITER = NexusValuesWriter(**_WRITER_ARGS)
_MAP_YAML_READER = YAMLReader(
    filename='map_config.yaml',
)
_MAP_VALUES_WRITER = NexusValuesWriter(
    filename='data.nxs', resize_axis=0, force_overwrite=True,
)
_NX_READER = NexusReader(
    filename='data.nxs',
)
_MAP_NX_WRITER = NexusWriter(
    filename='data.nxs', force_overwrite=True,
)
_STRAIN_NX_WRITER = NexusWriter(
    filename='data.nxs', force_overwrite=True,
)

# Cached loggers; avoids adding duplicate handlers on every processor
# instantiation (loggers are global singletons keyed by class name).
_PROC_LOGGER = None
_MAP_SLICE_PROC_LOGGER = None
_MAP_PROC_LOGGER = None

def _get_map_slice_processor(data, spec_file, scan_number):
    """Return a fresh ``MapSliceProcessor`` for a single scan.

    Passes ``data`` and ``modelmetaclass`` so that
    ``validate_processor_before`` auto-populates ``map_config`` from
    the ``MapConfig`` item already in ``data``.  Reuses the cached
    logger after the first instantiation.

    :param data: Pipeline data list containing at least one item with
        schema ``'common.models.map.MapConfig'``.
    :type data: list[CHAP.pipeline.PipelineData]
    :param spec_file: Absolute path to the SPEC file.
    :type spec_file: str
    :param scan_number: Number of the scan to process.
    :type scan_number: int
    :return: Processor ready to extract one scan slice from a map.
    :rtype: CHAP.common.map_utils.MapSliceProcessor
    """
    global _MAP_SLICE_PROC_LOGGER
    kwargs = dict(
        data=data, modelmetaclass=MapSliceProcessor,
        spec_file=spec_file, scan_number=scan_number,
        detectors=_DETECTORS_CONFIG["data"]["detectors"],
    )
    if _MAP_SLICE_PROC_LOGGER is None:
        proc = MapSliceProcessor(**kwargs)
        _MAP_SLICE_PROC_LOGGER = proc.logger
    else:
        proc = MapSliceProcessor(**kwargs, logger=_MAP_SLICE_PROC_LOGGER)
    return proc

def _get_map_processor(data):
    """Return a fresh ``MapProcessor`` configured for placeholder setup.

    Passes ``data`` and ``modelmetaclass`` so that
    ``validate_processor_before`` auto-populates ``config`` from the
    ``MapConfig`` item already in ``data``.  Reuses the cached logger
    after the first instantiation.

    :param data: Pipeline data list containing at least one item with
        schema ``'common.models.map.MapConfig'``.
    :type data: list[CHAP.pipeline.PipelineData]
    :return: Processor ready to build a map NeXus structure.
    :rtype: CHAP.common.processor.MapProcessor
    """
    global _MAP_PROC_LOGGER
    kwargs = dict(
        data=[*data, _detectors_config()], modelmetaclass=MapProcessor,
        remove_constant_dims=False, num_proc=1,
    )
    if _MAP_PROC_LOGGER is None:
        proc = MapProcessor(**kwargs)
        _MAP_PROC_LOGGER = proc.logger
    else:
        proc = MapProcessor(**kwargs, logger=_MAP_PROC_LOGGER)
    return proc


def _get_strain_analysis_processor():
    """Return a fresh ``StrainAnalysisProcessor`` configured for the
    ``update`` (not ``setup``) pass.

    Passes ``data=_init_data()`` and ``modelmetaclass`` so that pydantic's
    ``validate_processor_before`` auto-populates ``config`` from the
    cached ``StrainAnalysisConfig`` pipeline data.  Reuses the cached
    logger after the first instantiation to avoid adding duplicate log
    handlers.

    :return: Processor ready to run a strain-analysis update pass.
    :rtype: CHAP.edd.processor.StrainAnalysisProcessor
    """
    global _PROC_LOGGER
    if _PROC_LOGGER is None:
        proc = StrainAnalysisProcessor(
            data=_init_data(),
            modelmetaclass=StrainAnalysisProcessor,
            **_PROC_ARGS,
        )
        _PROC_LOGGER = proc.logger
    else:
        proc = StrainAnalysisProcessor(
            data=_init_data(),
            modelmetaclass=StrainAnalysisProcessor,
            logger=_PROC_LOGGER,
            **_PROC_ARGS,
        )
    return proc


def setup_raw(map_config_filename: str, map_data_filename: str):
    """Create an empty map NeXus container (placeholder structure, no
    detector data).

    Equivalent to running the following pipeline once per dataset:

    .. code-block:: yaml

        - common.YAMLReader:
            filename: map_config.yaml
            schema: common.models.map.MapConfig
        - common.MapProcessor:
            fill_data: false
            remove_constant_dims: false
            num_proc: 1
            detector_config:
              detectors:
              - id: 0
        - common.NexusWriter:
            filename: data.nxs
            force_overwrite: true

    :param map_config_filename: Map configuration YAML filename
        (relative to ``RUN_CFG.inputdir``).
    :type map_config_filename: str
    :param map_data_filename: NeXus output filename to create (relative
        to ``RUN_CFG.outputdir``).
    :type map_data_filename: str
    """
    # 1. Read map config YAML
    _MAP_YAML_READER.filename = map_config_filename
    map_cfg = _MAP_YAML_READER.read()
    data = [PipelineData(
        name='YAMLReader', data=map_cfg,
        schema='common.models.map.MapConfig')]

    # 2. Build placeholder NeXus map structure (no detector data)
    proc = _get_map_processor([*data, _DETECTORS_CONFIG])
    result = proc.process(data, fill_data=False)
    data.append(PipelineData(name='MapProcessor', data=result))

    # 3. Write map container
    _MAP_NX_WRITER.filename = map_data_filename
    _MAP_NX_WRITER.nxpath = None
    _MAP_NX_WRITER.write(data)


def setup_strain(filename: str, nxpath: str):
    """Run the full strain analysis setup pass and write the resulting
    NeXus group into an existing NeXus file.

    Equivalent to running the following pipeline once per dataset:

    .. code-block:: yaml

        - common.YAMLReader:
            filename: strain_analysis_config.yaml
            schema: edd.models.StrainAnalysisConfig
        - common.YAMLReader:
            filename: tth_calibration_result.yaml
            schema: edd.models.MCATthCalibrationConfig
        - common.NexusReader:
            filename: data.nxs
        - edd.StrainAnalysisProcessor:
            standalone: true
            setup: true
            update: false
            find_peaks: true
            skip_animation: true
            save_figures: false
        - common.NexusWriter:
            filename: data.nxs
            nxpath: /testflight-0212-b_dataset1_strain_analysis
            force_overwrite: true

    :param filename: NeXus filename to read from and write to (relative
        to ``RUN_CFG.inputdir`` / ``RUN_CFG.outputdir``).
    :type filename: str
    :param nxpath: NXpath in ``filename`` under which the strain
        analysis group will be written.
    :type nxpath: str
    """
    # Fresh data list each time
    data = _init_data()

    # 1. Read full NXS file
    _NX_READER.filename = filename
    nxroot = _NX_READER.read()
    data.append(PipelineData(name='NexusReader', data=nxroot))

    # 2. Process: setup pass (setup=True, update=False)
    global _PROC_LOGGER
    if _PROC_LOGGER is None:
        proc = StrainAnalysisProcessor(
            data=data, modelmetaclass=StrainAnalysisProcessor,
            **_SETUP_STRAIN_PROC_ARGS,
        )
        _PROC_LOGGER = proc.logger
    else:
        proc = StrainAnalysisProcessor(
            data=data, modelmetaclass=StrainAnalysisProcessor,
            logger=_PROC_LOGGER,
            **_SETUP_STRAIN_PROC_ARGS,
        )
    result = proc.process(data)
    for r in (result if isinstance(result, tuple) else [result]):
        data.append(r if isinstance(r, PipelineData) else
                    PipelineData(data=r))

    # 3. Append strain analysis group to NXS file
    _STRAIN_NX_WRITER.filename = filename
    _STRAIN_NX_WRITER.nxpath = nxpath
    _STRAIN_NX_WRITER.write(data)


def update_raw(map_config_filename: str,
               spec_file: str, scan_number: int,
               map_data_filename: str):
    """Write one scan's worth of raw map data into an existing NeXus file.

    Equivalent to running the following pipeline once per scan:

    .. code-block:: yaml

        - common.YAMLReader:
            filename: map_config.yaml
            schema: common.models.map.MapConfig
        - common.MapSliceProcessor:
            spec_file: /nfs/chess/previousid1a3/2024-1/schwalbach-3899-b/testfl\
ight-0212-b/spec.log
            scan_number: 2
            detectors:
            - id: 0
        - common.NexusValuesWriter:
            filename: data.nxs
            force_overwrite: true
            resize_axis: 0

    :param map_config_filename: Map configuration YAML filename
        (relative to ``RUN_CFG.inputdir``).
    :type map_config_filename: str
    :param spec_file: Path to the SPEC file for this scan (relative to
        ``RUN_CFG.inputdir`` or absolute).
    :type spec_file: str
    :param scan_number: Scan number to extract from ``spec_file``.
    :type scan_number: int
    :param map_data_filename: NeXus output filename (relative to
        ``RUN_CFG.outputdir``).
    :type map_data_filename: str
    """
    # 1. Read map config YAML (filename may vary per call)
    _MAP_YAML_READER.filename = map_config_filename
    map_cfg = _MAP_YAML_READER.read()
    data = [PipelineData(
        name='YAMLReader', data=map_cfg,
        schema='common.models.map.MapConfig')]

    # 2. Process one scan slice
    proc = _get_map_slice_processor(data, spec_file, scan_number)
    result = proc.process(data)
    data.append(PipelineData(name='MapSliceProcessor', data=result))

    # 3. Write results
    _MAP_VALUES_WRITER.filename = map_data_filename
    _MAP_VALUES_WRITER.write(data, filename=_MAP_VALUES_WRITER.filename)


def update_strain(filename: str, path_prefix: str,
                  scan_number: int, idx_slice: dict):
    """Write updated strain analysis results for one scan into an
    existing NeXus file.

    Equivalent to running the following pipeline:

    .. code-block:: yaml

        - edd.SliceNXdataReader:
            filename: data.nxs
            scan_number: 2
        - common.YAMLReader:
            filename: strain_analysis_config.yaml
            schema: edd.models.StrainAnalysisConfig
        - common.YAMLReader:
            filename: tth_calibration_result.yaml
            schema: edd.models.MCATthCalibrationConfig
        - edd.StrainAnalysisProcessor:
            standalone: true
            setup: false
            update: true
            find_peaks: true
            skip_animation: true
            save_figures: false
        - common.NexusValuesWriter:
            filename: data.nxs
            path_prefix: /testflight-0212-b_dataset1_strain_analysis/
            idx_slice:
               start: 0
               stop: 1
            resize_axis: 0
            force_overwrite: true

    :param filename: NeXus filename to read from and write to (relative
        to ``RUN_CFG.inputdir`` / ``RUN_CFG.outputdir``).
    :type filename: str
    :param path_prefix: NXpath prefix prepended to all dataset paths
        written by ``NexusValuesWriter``.
    :type path_prefix: str
    :param scan_number: Index of the NXdata slice to read.
    :type scan_number: int
    :param idx_slice: Slice configuration passed to ``NexusValuesWriter``
        as the write index.
    :type idx_slice: CHAP.common.models.IndexSliceConfig
    """
    # Fresh data list each time
    data = _init_data()

    # 1. Read raw input data
    _READER.filename = filename
    _READER.scan_number = scan_number
    nxroot = _READER.read()
    data.append(PipelineData(name='SliceNXdataReader', data=nxroot))

    # 2. Process: new instance per run (process() mutates data list)
    proc = _get_strain_analysis_processor()
    result = proc.process(data)

    # Normalize tuple-or-single result into data list
    for r in (result if isinstance(result, tuple) else [result]):
        data.append(r if isinstance(r, PipelineData) else
                    PipelineData(data=r))

    # 3. Write results
    _WRITER.filename = filename
    _WRITER.path_prefix = path_prefix
    if isinstance(idx_slice, dict):
        idx_slice = IndexSliceConfig(**idx_slice)
    _WRITER.idx_slice = idx_slice
    _WRITER.write(data, filename=_WRITER.filename)
