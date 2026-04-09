#!/usr/bin/env python3

"""Handle jobs for CHAP processing pipelines."""

from pathlib import Path

from app import get_logger
from app.state import get_state

logger = get_logger("pipeline_manager")

def submit_pipeline(dataset_name, pipeline_name):
    """Submit a CHAP processing pipeline job via ``qsub``.

    Constructs a ``qsub -- CHAP <pipeline.yaml> -p <pipeline_name>``
    command for the dataset's analysis directory and logs it.  The
    actual :func:`subprocess.Popen` call is currently commented out.

    :param dataset_name: Name of the dataset whose pipeline to submit.
    :type dataset_name: str
    :param pipeline_name: Pipeline stage name passed to CHAP via ``-p``
        (e.g. ``"setup"`` or ``"update_1"``).
    :type pipeline_name: str
    """
    pipeline = Path(get_state().analysis_root) / dataset_name / "pipeline.yaml"

    cmd = [
        "qsub",
        "--",
        "CHAP",
        str(pipeline),
        "-p",
        pipeline_name,
    ]

    logger.info(f"Submitting job: {' '.join(cmd)}")
    # subprocess.Popen(cmd)
