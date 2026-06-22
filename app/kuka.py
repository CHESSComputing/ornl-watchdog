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


def kuka_collect_point(dataset, location, callback=None):
    state = get_state()

    def position_and_build():
        success, labx, laby, labz = position_kuka(location)
        if not success:
            logger.error(
                "Positioning failed, skipping data collection and processing"
            )
            return None
        logger.debug("Sending SPEC commands")
        return [
            f"newsample \"{dataset}\" 0",
            f"umv {state.labx_motor} {labx}",
            f"umv {state.laby_motor} {laby}",
            f"umv {state.labz_motor} {labz}",
            state.scan_command,
        ]

    state.spec.enqueue(position_and_build, callback=callback)


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
    state = get_state()
    success = False
    attempt = 1
    pose, labx, laby, labz = location_to_pose(location)
    request_data = {
        "target_pose": pose,
        "control_frame": "lab",
    }
    while not success and (attempt <= max_retries or max_retries < 0):
        logger.info(
            f"POST {request_data} to {state.kuka_positioner_url}/move_kuka "
            f"(attempt {attempt}/{max_retries})"
        )
        resp = requests.post(
            url=f"{state.kuka_positioner_url}/move_kuka",
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
            if resp.status_code in (500, 501, 502):
                # Sleep & try again
                # 500: Robot already in motion
                # 501: Failed to move to target pose
                # 502: Kuka unreachable?
                time.sleep(sleep_duration)
            elif resp.status_code == 400:
                # Invalid position, DO NOT try again
                logger.error("KUKA POSITIONING FAILED")
                break
    return success, labx, laby, labz


def location_to_pose(location):
    """Normalize (labx, laby, labz) coordinate pairs to 4d matrix
    representing an actual Kuka pose.

    NB: Moving a motor in its positive direction corresponds to moving
    the measured point in the sample's reference frame in the positive
    direction, too. So we _do not_ need to multiply motor positions by
    -1 to get the corresponding sample coordinates.

    :param location: Either a (labx, laby, labz) corrdinate triplet or
        a 4D pose matrix
    :returns: A 4D pose matrix, lab X coorindate, lab Y coordinate,
        lab Z coordinate
    """
    state = get_state()
    pose, labx, laby, labz = None, None, None, None
    if len(location) == 3:
        # labx, laby, labz coordinates were given; transform to pose
        labx, laby, labz = location
        v = np.asarray([labx, laby, labz, 0, 0, 0]) * 0.001
        position = exp_se3(v)
        lab_to_flange = np.asarray(state.kuka_sample_to_flange) @ np.asarray(state.kuka_nominal_lab_to_sample) @ np.asarray(position)
        flange_to_lab = np.linalg.inv(lab_to_flange)
        pose = flange_to_lab
    else:
        raise NotImplementedError
        # a pose was given; transform to labx, laby, labz coorinates
        pose = np.asarray(location)
        labx = pose[0, 3]
        laby = pose[1, 3]
        labz = pose[2, 3]
    if isinstance(pose, np.ndarray):
        pose = pose.tolist()
    return pose, labx, laby, labz


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
