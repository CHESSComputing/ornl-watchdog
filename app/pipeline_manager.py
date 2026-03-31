#!/usr/bin/env python3

"""Handle jobs for CHAP processing pipelines."""

import logging
from pathlib import Path

from app import ANALYSIS_ROOT, get_logger

logger = get_logger("pipeline_manager")

def submit_pipeline(dataset_name, pipeline_name):
    """Submit a job to set up the processing environment."""
    pipeline = Path(ANALYSIS_ROOT) / dataset_name / "pipeline.yaml"

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
