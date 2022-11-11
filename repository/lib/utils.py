"""
Useful utilities for interacting with ARTIQ and the AION / ICL setup
"""
from typing import List

from artiq.experiment import HasEnvironment


def get_suservo_channels(hasEnv: HasEnvironment) -> List[str]:
    """Get all possible SUServo channels, including aliases

    Example usage (from an EnvExperiment)::

        list_of_channels = get_suservo_channel(self)

    Args:
        hasEnv (HasEnvironment): An initiated HasEnvironment object

    Returns:
        List[str]: List of names of all SUServo channels
    """
    raw_channels = [
        k
        for k, v in hasEnv.get_device_db().items()
        if (
            ("type" in v and v["type"] == "local")
            and ("module" in v and v["module"] == "artiq.coredevice.suservo")
            and ("class" in v and v["class"] == "Channel")
        )
    ]

    alias_channels = [
        k
        for k, v in hasEnv.get_device_db().items()
        if (isinstance(k, str) and isinstance(v, str) and v in raw_channels)
    ]

    return alias_channels + raw_channels
