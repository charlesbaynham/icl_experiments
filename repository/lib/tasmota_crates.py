"""Helpers for power-cycling the ARTIQ crates via Tasmota smart sockets.

These helpers are shared by the reboot and shutdown utility experiments. The
``confirm_with_code`` helper implements the random-code confirmation pattern
used to guard against accidental power events.
"""

import logging
import random

import requests
from artiq.experiment import HasEnvironment

logger = logging.getLogger(__name__)

# List of tasmota sockets to control. Power-off iterates this list in order;
# power-on iterates in the same order so dependencies come up before dependants.
TASMOTA_HOSTS = [
    "tasmota-artiq-master",
    "tasmota-artiq-red",
    "tasmota-artiq-blue",
    "tasmota-artiq-plantroom",
]

TASMOTA_OVEN = "10.137.1.34"

POWER_ON_CMD = "http://{}/cm?cmnd=Power%20on"
POWER_OFF_CMD = "http://{}/cm?cmnd=Power%20off"


def power_off_all(include_oven: bool = False) -> None:
    """Send a power-off command to every Tasmota host in ``TASMOTA_HOSTS``."""
    for host in TASMOTA_HOSTS:
        logger.info("Turning off %s", host)
        requests.get(POWER_OFF_CMD.format(host))
    if include_oven:
        logger.info("Turning off oven (%s)", TASMOTA_OVEN)
        requests.get(POWER_OFF_CMD.format(TASMOTA_OVEN))


def power_on_all(include_oven: bool = False) -> None:
    """Send a power-on command to every Tasmota host in ``TASMOTA_HOSTS``."""
    for host in TASMOTA_HOSTS:
        logger.info("Turning on %s", host)
        requests.get(POWER_ON_CMD.format(host))
    if include_oven:
        logger.info("Turning on oven (%s)", TASMOTA_OVEN)
        requests.get(POWER_ON_CMD.format(TASMOTA_OVEN))


def confirm_with_code(experiment: HasEnvironment, dataset_name: str) -> bool:
    """Two-step confirmation guarded by a random code stored in a dataset.

    Reads the current target code from ``dataset_name``, generates a fresh
    code and writes it back, then returns ``True`` only if the experiment's
    ``confirmation_code`` argument matches the *previously stored* code.

    The experiment must already have a ``confirmation_code`` integer attribute
    (set up by ``setattr_argument`` in ``build()``).
    """
    target_code = experiment.get_dataset(dataset_name, default=0, archive=False)
    new_code = random.randint(100, 999)

    experiment.set_dataset(
        dataset_name, new_code, archive=True, broadcast=True, persist=False
    )

    if experiment.confirmation_code == target_code:
        return True

    logger.warning(
        "Are you sure? If so, enter the code %d and run this experiment again",
        new_code,
    )
    return False
