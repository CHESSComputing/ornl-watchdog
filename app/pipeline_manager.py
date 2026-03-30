#!/usr/bin/env python3

"""Handle jobs for CHAP processing pipelines."""

import logging

from . import ANALYSIS_ROOT

logger = get_logger("pipeline_manager")

def submit_pipeline(dataset_name, pipeline_name):
    """Submit a job to set up the processing environment."""
    pipeline = ANALYSIS_ROOT / dataset_name / "pipeline.yaml"

    cmd = [
        "qsub",
        "--",
        "CHAP",
        str(pipeline),
        "-p",
        profile
    ]

    logger.info("Submitting:", " ".join(cmd))
    subprocess.Popen(cmd)