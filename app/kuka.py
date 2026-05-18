#!/usr/bin/env python3

"""Communicate with the Kuka positioner application via HTTPS.
"""

import logging
import numpy as np
import requests
import time

from app import get_logger
from app.state import get_state

logger = get_logger("kuka")


def location_to_pose(location):
    """Normalize (labx, labz) coordinate pairs to 4d matrix
    representing an actual Kuka pose.

    :param location: Either a (labx, labz) corrdinate pair or a 4D
        pose matrix
    :returns: A 4D pose matrix
    """
    pose = None
    if len(location) == 2:
        # labx, labz coordinates were given; transform it to pose
        labx, labz = location
        v = np.asarray([labx, 0, labz, 0, 0, 0])
        position = exp_se3(v)
        pose = get_state().kuka_transform_matrix * position
    else:
        # a pose was already given
        pose = location
    return pose


def position_kuka(location, max_retries=-1, sleep_duration=5):
    """Send a pose command to the Kuka positioner via HTTPS POST.

    Retries on non-200 responses up to *max_retries* times.  A value of
    ``-1`` (the default) retries indefinitely until a 200 response is
    received.

    :param location: New location at which to measure data,
    :param max_retries: Maximum number of POST attempts.  ``-1`` means
        retry indefinitely.
    :type max_retries: int
    :param sleep_duration: Time in seconds to sleep between retries
        for positioning the Kuka when applicable. Defaults to 5.
    :type sleep_duration: float, optional
    """
    success = False
    attempt = 1
    request_data = {"pose_data": location_to_pose(location)}
    while not success and (attempt <= max_retries or max_retries < 0):
        logger.info(
            f"POST {request_data} to {state.kuka_positioner_server_url} "
            f"(attempt {attempt}/{max_retries})"
        )
        resp = requests.post(
            url=state.kuka_positioner_server_url,
            json=request_data,
            timeout=state.spec_timeout, # Use same timeout as SPEC for now
        )
        logger.info(f"Kuka positioner response: {resp.text}")
        attempt += 1
        if resp.status_code == 200:
            success = True
            logger.info("Success")
        else:
            logger.error(f"Error: {resp.reason}")
            if resp.status_code in (500, 501):
                # Sleep & try again
                # 500: Robot already in motion
                # 501: Failed to mode to target pose
                time.sleep(sleep_duration)
            elif resp.status_code == 400:
                # Invalid position, DO NOT try again
                logger.error("KUKA POSITIONING FAILED")
                break


def exp_so3(v: np.ndarray):
    """Compute the exponential map of an so3 vector to create an SO3
    rotation matrix"""
    theta = np.linalg.norm(v)
    if theta < 1e-12:
        return np.eye(3)
    v = v / theta
    V = np.array(((0, -v[2], v[1]), (v[2], 0, -v[0]), (-v[1], v[0], 0)))

    return (
        np.cos(theta) * np.eye(3)
        + np.sin(theta) * V
        + (1 - np.cos(theta)) * np.outer(v, v)
    )

def exp_se3(v: np.ndarray):
    """Compute the exponential map of an se3 vector to create an SE3
    transformation matrix"""
    T = np.eye(4)
    T[:3, :3] = exp_so3(v[3:])
    T[:3, 3] = v[:3]
    return T
