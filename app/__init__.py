"""Module contents."""

# SPEC connection parameters
# Hostname or IP address of the spec server:
SPEC_HOST = 'localhost'
# Port number of the spec server:
SPEC_PORT = 6511

# SPEC data collection parameters
# Timeout for SPEC commands in seconds:
SPEC_TIMEOUT = 30
# Name / mnemonic of labx motor in SPEC:
LABX_MOTOR = 'labx'
# Name / mnemonic of labz motor in SPEC:
LABZ_MOTOR = 'labz'
# Number of points in each tseries acquisition:
TSERIES_NPTS = 10
# Exposure time for each point in the tseries acquisition in seconds:
TSERIES_EXPOSURE = 0.1

# File watcher parameters
# Root directory to watch for new datasets and updates:
WATCH_ROOT = '/nfs/chess/raw/<cycle>/<station>/<btr>/autonomous_experiment/'

# Analysis job parameters
# Root directory for analysis outputs:
ANALYSIS_ROOT = '/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>'
# Full abosulte path to the EDD configuration to use for processing new datasets:
CALIBRATION_YAML = '/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/calibration_config.yaml'
# Full absolute path to the strain analysis configuration to use for processing new datasets:
STRAIN_ANALYSIS_YAML = '/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/strain_analysis_config.yaml'

# Dataset registry for state recovery in case of crashes
# Full absolute path to the dataset registry YAML file:
REGISTRY_YAML = "/nfs/chess/aux/reduced_data/cycles/<cycle>/<station>/<btr>/dataset_registry.yaml"

# Do not modify below this line

def get_logger(name=__name__, log_level="DEBUG"):
    """Set up a logger with the specified name and log level."""
    import logging

    logger = logging.getLogger(name)
    log_level = getattr(logging, log_level.upper())
    logger.setLevel(log_level)
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter(
        '{asctime}: {name:20}: {levelname}: {message}',
        datefmt='%Y-%m-%d %H:%M:%S', style='{'))
    logger.addHandler(log_handler)
    logger.handlers = [log_handler]
    return logger

from app.state_registry import load_registry
DATASETS = load_registry()

from app.spec_controller import SpecController
SPEC = SpecController(SPEC_HOST, SPEC_PORT)
