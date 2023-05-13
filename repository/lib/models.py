"""
Models
======

Models for data structures. These classes define data structures that can be
used in other parts of the code and can optionally implement data validation.

By using `Pydantic <https://docs.pydantic.dev/latest/>`_. dataclasses, these
models act as normal python classes and so are fully compatible with ARTIQ
kernels.
"""
from typing import Optional

from pydantic.dataclasses import dataclass


@dataclass
class SUServoedBeam:
    """
    A simple class that holds information about a beam to be controlled via a
    SUServo.

    """

    name: str
    frequency: float
    attenuation: float
    suservo_device: str
    shutter_device: Optional[str] = None
    shutter_delay: float = 0.0
