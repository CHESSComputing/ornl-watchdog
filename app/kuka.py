#!/usr/bin/env python3

"""Communicate with the Kuka positioner application via HTTPS.
"""

import logging
import requests

from app import get_logger


logger = get_logger("kuka")


def position_kuka(position, max_retries=-1):
    """Send a position command to the Kuka positioner via HTTPS POST.

    Retries on non-200 responses up to *max_retries* times.  A value of
    ``-1`` (the default) retries indefinitely until a 200 response is
    received.

    :param position: Position data posted as JSON to the Kuka server.
    :param max_retries: Maximum number of POST attempts.  ``-1`` means
        retry indefinitely.
    :type max_retries: int
    """
    success = False
    attempt = 1
    request_data = position # OK as is, or additional treatment needed?
    while not success and (attempt <= max_retries or max_retries < 0):
        logger.info(
            f"POST {j_a} to {state.kuka_positioner_server_url} "
            f"(attempt {attempt}/{max_retries})"
        )
        resp = requests.post(
            url=state.kuka_positioner_server_url,
            json=joint_angles,
            timeout=state.spec_timeout, # Use same timeout as SPEC for now      
        )
        logger.info(f"Kuka positioner response: {resp.text}")
        attempt += 1
        if resp.status_code == 200:
            success = True
            logger.info("Success")
        else:
            logger.error(f"Error: {resp.reason}")
