#

"""Daemon for quickly updating raw and processed EDD data."""
# Slow imports (only need to do once in daemon)
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

# Global run config
RUN_CFG = RunConfig(log_level='debug')
def update_runcfg(inputdir, outputdir):
    """Update the global run configuration with new I/O directories.

    Reinitializes ``RUN_CFG`` so that all subsequent pipeline calls
    resolve relative filenames against the new directories.

    :param inputdir: Absolute path to the input directory.
    :type inputdir: str
    :param outputdir: Absolute path to the output directory.
    :type outputdir: str
    """
    global RUN_CFG
    RUN_CFG = RunConfig(
        inputdir=inputdir,
        outputdir=outputdir,
        log_level='debug'
    )
update_runcfg(
    inputdir='/nfs/chess/scratch/user/kls286/edd/ornl',
    outputdir='/nfs/chess/scratch/user/kls286/edd/ornl',
)

# Pre-read the static YAML configs once; cache raw dicts
def _read_yaml(filename, schema):
    """Read a YAML file and return a tagged ``PipelineData`` object.

    Resolves ``filename`` against ``RUN_CFG.inputdir`` and reads the
    YAML contents into a ``PipelineData`` dict tagged with ``schema``.
    Intended to be called once at startup to cache static configurations.

    :param filename: YAML filename (relative to ``RUN_CFG.inputdir``).
    :type filename: str
    :param schema: Fully qualified CHAP schema name used to tag the
        returned ``PipelineData`` (e.g.
        ``'edd.models.StrainAnalysisConfig'``).
    :type schema: str
    :return: Pipeline data item carrying the parsed YAML contents.
    :rtype: CHAP.pipeline.PipelineData
    """
    r = YAMLReader(filename=filename, schema=schema, **RUN_CFG.model_dump())
    return PipelineData(name='YAMLReader', data=r.read(), schema=schema)

_STRAIN_CFG = _read_yaml(
    'strain_analysis_config.yaml',
    'edd.models.StrainAnalysisConfig'
)
_TTH_CFG = _read_yaml(
    'tth_calibration_result.yaml',
    'edd.models.MCATthCalibrationConfig'
)
_DETECTORS_CONFIG = _read_yaml(
    'xps23_config.yaml',
    'common.models.map.DetectorConfig'
)
_INIT_DATA = [_STRAIN_CFG, _TTH_CFG]

# Fixed args for the processor and writer (everything except the
# per-run fields)
_READER_ARGS = dict(
    filename='data.nxs',
    scan_number=0,
    **RUN_CFG.model_dump()
)
_PROC_ARGS = dict(
    standalone=True, setup=False, update=True,
    find_peaks=True, skip_animation=True, save_figures=False,
    **RUN_CFG.model_dump()
)
_SETUP_STRAIN_PROC_ARGS = dict(
    standalone=True, setup=True, update=False,
    find_peaks=True, skip_animation=True, save_figures=False,
    **RUN_CFG.model_dump()
)
_WRITER_ARGS = dict(
    filename='data.nxs',
    path_prefix='/testflight-0212-b_dataset1_strain_analysis/',
    resize_axis=0, force_overwrite=True,
    **RUN_CFG.model_dump()
)

# Module-level singletons; filenames are mutated per call to avoid
# re-running pydantic validation (which resolves paths against inputdir
# / outputdir once at construction time).
_READER = SliceNXdataReader(**_READER_ARGS)
_WRITER = NexusValuesWriter(**_WRITER_ARGS)
_MAP_YAML_READER = YAMLReader(filename='map_config.yaml', **RUN_CFG.model_dump())
_MAP_VALUES_WRITER = NexusValuesWriter(
    filename='data.nxs', resize_axis=0, force_overwrite=True,
    **RUN_CFG.model_dump())
_NX_READER = NexusReader(filename='data.nxs', **RUN_CFG.model_dump())
_MAP_NX_WRITER = NexusWriter(
    filename='data.nxs', force_overwrite=True, **RUN_CFG.model_dump())
_STRAIN_NX_WRITER = NexusWriter(
    filename='data.nxs', force_overwrite=True, **RUN_CFG.model_dump())

# Cached loggers; avoids adding duplicate handlers on every processor
# instantiation (loggers are global singletons keyed by class name).
_PROC_LOGGER = None
_MAP_SLICE_PROC_LOGGER = None
_MAP_PROC_LOGGER = None


def get_StrainAnalysisProcessor():
    """Return a fresh ``StrainAnalysisProcessor`` configured for the
    ``update`` (not ``setup``) pass.

    Passes ``data=_INIT_DATA`` and ``modelmetaclass`` so that pydantic's
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
            data=_INIT_DATA,
            modelmetaclass=StrainAnalysisProcessor,
            **_PROC_ARGS,
        )
        _PROC_LOGGER = proc.logger
    else:
        proc = StrainAnalysisProcessor(
            data=_INIT_DATA,
            modelmetaclass=StrainAnalysisProcessor,
            logger=_PROC_LOGGER,
            **_PROC_ARGS,
        )
    return proc


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
        **RUN_CFG.model_dump(),
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
        data=[*data, _DETECTORS_CONFIG], modelmetaclass=MapProcessor,
        remove_constant_dims=False, num_proc=1,
        # detector_config={'detectors': [{'id': 0}]},
        **RUN_CFG.model_dump(),
    )
    if _MAP_PROC_LOGGER is None:
        proc = MapProcessor(**kwargs)
        _MAP_PROC_LOGGER = proc.logger
    else:
        proc = MapProcessor(**kwargs, logger=_MAP_PROC_LOGGER)
    return proc


import queue as _queue
import threading

_task_queue = _queue.Queue()


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
            spec_file: /nfs/chess/previousid1a3/2024-1/schwalbach-3899-b/testflight-0212-b/spec.log
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
    _MAP_YAML_READER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.inputdir, map_config_filename)))
    map_cfg = _MAP_YAML_READER.read()
    data = [PipelineData(
        name='YAMLReader', data=map_cfg,
        schema='common.models.map.MapConfig')]

    # 2. Process one scan slice
    abs_spec_file = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.inputdir, spec_file)))
    proc = _get_map_slice_processor(data, abs_spec_file, scan_number)
    result = proc.process(data)
    data.append(PipelineData(name='MapSliceProcessor', data=result))

    # 3. Write results
    _MAP_VALUES_WRITER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.outputdir, map_data_filename)))
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
    # Fresh data list each time; deep-copy so get_config(remove=True)
    # doesn't drain the cached seeds
    data = deepcopy(_INIT_DATA)

    # 1. Read raw input data
    _READER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.inputdir, filename)))
    _READER.scan_number = scan_number
    nxroot = _READER.read()
    data.append(PipelineData(name='SliceNXdataReader', data=nxroot))

    # 2. Process: new instance per run (process() mutates data list)
    proc = get_StrainAnalysisProcessor()
    result = proc.process(data)

    # Normalize tuple-or-single result into data list
    for r in (result if isinstance(result, tuple) else [result]):
        data.append(r if isinstance(r, PipelineData) else
                    PipelineData(data=r))

    # 3. Write results
    _WRITER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.outputdir, filename)))
    _WRITER.path_prefix = path_prefix
    _WRITER.idx_slice = idx_slice
    _WRITER.write(data, filename=_WRITER.filename)


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
    _MAP_YAML_READER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.inputdir, map_config_filename)))
    map_cfg = _MAP_YAML_READER.read()
    data = [PipelineData(
        name='YAMLReader', data=map_cfg,
        schema='common.models.map.MapConfig')]

    # 2. Build placeholder NeXus map structure (no detector data)
    proc = _get_map_processor([*data, _DETECTORS_CONFIG])
    result = proc.process(data, fill_data=False)
    data.append(PipelineData(name='MapProcessor', data=result))

    # 3. Write map container
    _MAP_NX_WRITER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.outputdir, map_data_filename)))
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
    # Fresh data list with cached YAML configs
    data = deepcopy(_INIT_DATA)

    # 1. Read full NXS file
    _NX_READER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.inputdir, filename)))
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
    _STRAIN_NX_WRITER.filename = os.path.normpath(os.path.realpath(
        os.path.join(RUN_CFG.outputdir, filename)))
    _STRAIN_NX_WRITER.nxpath = nxpath
    _STRAIN_NX_WRITER.write(data)


# import time
# t0 = time.time()
# update_strain(
#     filename='data.nxs',
#     path_prefix='/testflight-0212-b_dataset1_strain_analysis/',
#     scan_number=2,
#     idx_slice=IndexSliceConfig(**{'start':0, 'stop': 1}),
# )
# tf = time.time()
# print(f'execute_pipeline in {tf-t0} s')
# execute_pipeline('data.nxs', scan_number=3, idx_slice=IndexSliceConfig(**{'start':1, 'stop': 2}), path_prefix='/testflight-0212-b_dataset1_strain_analysis/')
# tf2 = time.time()
# print(f'execute_pipeline in {tf2-tf} s')

from flask import Flask, jsonify, request
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s: %(name)-20s (L%(lineno)d): %(levelname)s: %(message)s',
)
app = Flask(__name__)


def _worker():
    while True:
        task, args, kwargs = _task_queue.get()
        try:
            task(*args, **kwargs)
        except Exception as exc:
            app.logger.error(f'Task failed: {exc}')
        finally:
            _task_queue.task_done()

threading.Thread(target=_worker, daemon=True).start()


def _do_setup(map_config_filename, map_data_filename, filename, nxpath):
    app.logger.debug(f'setup_raw({map_config_filename}, {map_data_filename})')
    setup_raw(map_config_filename, map_data_filename)
    app.logger.debug(f'setup_strain({filename}, {nxpath})')
    setup_strain(filename, nxpath)
    app.logger.info('Done with setup')


def _do_update(map_config_filename, spec_file, scan_number, map_data_filename,
               filename, path_prefix, idx_slice):
    app.logger.debug(
        f'update_raw({map_config_filename}, {spec_file}, '
        f'{scan_number}, {map_data_filename})')
    update_raw(map_config_filename, spec_file, scan_number, map_data_filename)
    app.logger.debug(
        f'update_strain({filename}, {path_prefix}, '
        f'{scan_number}, {idx_slice})')
    update_strain(filename, path_prefix, scan_number, idx_slice)
    app.logger.info('Done with update')


@app.route('/setup', methods=['POST'])
def setup():
    """Flask endpoint: run the full setup sequence for a new dataset.

    Expects a JSON body with the following fields:

    - ``map_config_filename`` (str): Map config YAML filename.
    - ``map_data_filename`` (str): NeXus output filename for raw map.
    - ``filename`` (str): NeXus filename for strain analysis output.
    - ``nxpath`` (str): NXpath in ``filename`` for the strain group.

    :return: ``{"status": "ok"}`` on success, or
        ``{"error": "..."}`` with an appropriate HTTP status code.
    :rtype: flask.Response
    """
    body = request.get_json(force=True, silent=True) or {}

    map_config_filename = body.get('map_config_filename')
    map_data_filename = body.get('map_data_filename')
    filename = body.get('filename')
    nxpath = body.get('nxpath')

    missing = [k for k, v in {
        'map_config_filename': map_config_filename,
        'map_data_filename': map_data_filename,
        'filename': filename,
        'nxpath': nxpath,
    }.items() if v is None]
    if missing:
        return jsonify({'error': f'Missing required parameters: {missing}'}), 400

    app.logger.info(f'Queuing setup for dataset {filename}')
    _task_queue.put((_do_setup, (map_config_filename, map_data_filename, filename, nxpath), {}))
    return jsonify({'status': 'queued'}), 202


@app.route('/update', methods=['POST'])
def update():
    """Flask endpoint: write one scan's raw and strain data into an
    existing dataset.

    Expects a JSON body with the following fields:

    - ``map_config_filename`` (str): Map config YAML filename.
    - ``spec_file`` (str): Path to the SPEC file for the scan.
    - ``scan_number`` (int): Scan number to process.
    - ``map_data_filename`` (str): NeXus filename for raw map output.
    - ``filename`` (str): NeXus filename for strain analysis output.
    - ``path_prefix`` (str): NXpath prefix for the strain writer.
    - ``idx_slice`` (dict): Slice config with ``start`` and ``stop``
      keys, e.g. ``{"start": 0, "stop": 1}``.

    :return: ``{"status": "ok"}`` on success, or
        ``{"error": "..."}`` with an appropriate HTTP status code.
    :rtype: flask.Response
    """
    body = request.get_json(force=True, silent=True) or {}

    map_config_filename = body.get('map_config_filename')
    spec_file = body.get('spec_file')
    scan_number = body.get('scan_number')
    map_data_filename = body.get('map_data_filename')
    filename = body.get('filename')
    path_prefix = body.get('path_prefix')
    idx_slice_dict = body.get('idx_slice')

    missing = [k for k, v in {
        'map_config_filename': map_config_filename,
        'spec_file': spec_file,
        'scan_number': scan_number,
        'map_data_filename': map_data_filename,
        'filename': filename,
        'path_prefix': path_prefix,
        'idx_slice': idx_slice_dict,
    }.items() if v is None]
    if missing:
        return jsonify({'error': f'Missing required parameters: {missing}'}), 400

    try:
        idx_slice = IndexSliceConfig(**idx_slice_dict)
        scan_number = int(scan_number)
    except Exception as exc:
        return jsonify({'error': f'Invalid parameter value: {exc}'}), 400

    app.logger.info(f'Queuing update for dataset {filename}, scan {scan_number}')
    _task_queue.put((_do_update, (map_config_filename, spec_file, scan_number,
                                  map_data_filename, filename, path_prefix, idx_slice), {}))
    return jsonify({'status': 'queued'}), 202


if __name__ == "__main__":
    app.run(debug=True)
