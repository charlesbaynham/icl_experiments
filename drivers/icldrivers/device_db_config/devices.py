import logging

from ._aliases import aliases as _aliases
from ._device_db import device_db as _db
from ._non_core_devices import get_non_core_devices as get_non_core_devices


logger = logging.getLogger(__name__)
if logger.level <= logging.INFO:
    import pprint


def get_device_db(simulation_mode=False):
    """
    Returns the device_db, including both hardware identifiers and aliases.
    """

    db = _db.copy()

    # Append our own peripheral devices
    db = _append_non_core(db, simulation_mode)

    # Append our own aliases, describing the purposes of the channels
    db = _append_aliases(db)

    logger.info("DeviceDB import performed, resulting in device_db:")
    logger.info(pprint.pformat(db))

    return db


def _append_aliases(db: dict):
    # Merge dicts
    return {**db, **_aliases}


def _append_non_core(db: dict, simulation_mode=False):
    non_core = get_non_core_devices(simulation_mode)

    # Merge dicts
    return {**db, **non_core}
