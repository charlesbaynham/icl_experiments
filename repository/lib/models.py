"""
Models for data structures

These classes define data structures that can be used in other parts of the code
and can optionally implement data validation.

By using `Pydantic <https://docs.pydantic.dev/latest/>`_. dataclasses, these
models act as normal python classes and so are fully compatible with ARTIQ
kernels.
"""
from typing import List
from typing import Optional

from pydantic.dataclasses import dataclass


@dataclass
class BeamInfo:
    """
    A simple class that holds information about a beam delivered via an AOM

    This describes AOMs driven by SUServos or Urukuls, with or without supporting shutters
    """

    name: str
    frequency: float
    attenuation: float
    urukul_or_suservo_device: str
    is_urukul: bool = False
    shutter_device: Optional[str] = None
    shutter_delay: float = 0.0
    setpoint: float = 0.0
    "A setpoint in volts which should be attainable under all circumstances. If this power cannot be reached, the experiment has permission to misbehave"
    servo_enabled: bool = False
    photodiode_offset: float = 0.0
    """
    Offset read by the photodiode when the light is off.

    Relevant only when servoing beams with very low amplitudes, this number should
    be added to all setpoints before setting them.
    """
