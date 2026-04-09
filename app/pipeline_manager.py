#!/usr/bin/env python3

"""Handle jobs for CHAP processing pipelines."""

from pathlib import Path

from app import get_logger
from app.state import get_state

logger = get_logger("pipeline_manager")

def submit_pipeline(dataset_name, pipeline_name):
    """Submit a job to set up the processing environment."""
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
