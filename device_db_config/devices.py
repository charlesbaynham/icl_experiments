import importlib
import logging

from . import _aliases as aliases
from . import _device_db as generated_device_db
from . import _non_core_devices as non_core_devices


logger = logging.getLogger(__name__)
if logger.level <= logging.INFO:
    import pprint


def get_device_db(simulation_mode=False):
    """
    Returns the device_db, including both hardware identifiers and aliases.

    This function always reloads the libraries even if they have already been imported.
    """

    # Force reload of the modules in case they have been updated
    importlib.reload(aliases)
    importlib.reload(generated_device_db)
    importlib.reload(non_core_devices)

    db = generated_device_db.device_db.copy()

    # Append our own peripheral devices
    db = _append_non_core(db, simulation_mode)

    # Append our own aliases, describing the purposes of the channels
    db = _append_aliases(db)

    logger.info("DeviceDB import performed, resulting in device_db:")
    logger.info(pprint.pformat(db))

    return db


def _append_aliases(db: dict):
    # Merge dicts
    return {**db, **aliases.aliases}


def _append_non_core(db: dict, simulation_mode=False):
    non_core = non_core_devices.get_non_core_devices(simulation_mode)

    # Merge dicts
    return {**db, **non_core}
