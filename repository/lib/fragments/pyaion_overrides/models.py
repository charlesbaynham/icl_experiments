"""
Models for data structures

These classes define data structures that can be used in other parts of the code
and can optionally implement data validation.

By using `Pydantic <https://docs.pydantic.dev/latest/>`_. dataclasses, these
models act as normal python classes and so are fully compatible with ARTIQ
kernels.
"""

from functools import wraps
from typing import List
from typing import Optional

import pydantic
import pydantic.dataclasses
from pyaion.fragments.suservo import DEFAULT_KI as DEFAULT_SUSERVO_KI
from pydantic import ConfigDict
from pydantic import Field


# Default to forbid extra fields in dataclasses
@wraps(pydantic.dataclasses.dataclass)
def dataclass(fn):
    return pydantic.dataclasses.dataclass(
        fn,
        config=ConfigDict(
            extra=pydantic.Extra.forbid,
        ),
    )


@dataclass
class SUServoedBeam:
    """
    A simple class that holds information about a beam to be controlled via a
    SUServo
    """

    name: str
    frequency: float
    attenuation: float
    suservo_device: str
    shutter_device: Optional[str] = None
    shutter_delay: float = 0.0
    setpoint: float = 0.0
    "A setpoint in volts which should be attainable under all circumstances. If this power cannot be reached, the experiment has permission to misbehave"
    servo_enabled: bool = False
    initial_amplitude: float = 1.0
    "Amplitude when beam is initiated. If the servo is enabled, this will be the start point, otherwise it will be set throughout"
    photodiode_offset: float = 0.0
    """
    Offset read by the photodiode when the light is off.

    Relevant only when servoing beams with very low amplitudes, this number should
    be added to all setpoints before setting them.
    """
    pgia_setting: int = Field(default=0, ge=0, le=3)
    """
    Value of the Sampler's programmable gain instrumentation amplifier

    Must be 0, 1, 2 or 3. 0 is 1x, 1 is 10x, 2 is 100x and 3 is 1000x.
    """
    kI_loop_constant: float = DEFAULT_SUSERVO_KI
    """
    kI loop constant for the SUServo lock. Irrelevant if the servo is not enabled. Should usually be negative.
    """


@dataclass
class UrukuledBeam:
    """
    A simple class that holds information about a beam to be controlled via an Urukul channel.

    Includes ability to change the amplitude as well as attenuation, avoiding global setting of attenuation.
    """

    name: str
    frequency: float
    attenuation: float
    urukul_device: str
    amplitude: float = 1.0
    shutter_device: Optional[str] = None
    shutter_delay: Optional[float] = 0.0


@dataclass
class ThorlabsShutter:
    """
    A simple class that holds information about a Thorlabs SH05/M shutter. Characterisation of the shutter required
    to determine the linear and quadratic regions of operation. This is used with the Thorlabs_shutter fragment to get
    accurate outputs from the shutter at short times.

    Parameters:
    min_duration: smallest duration the shutter can output
    threshold_duration: where the shutter goes from linear to quadratic
    delay: Delay from requesting turn on.
    quad_fit_param: [a,b,c] from ax**2 +bx +c
    linear_fit_param: [b,c] from bx +c
    """

    name: str
    min_duration: float
    delay_rise: float
    delay_fall: float
    thresh_duration: float
    quad_fit_param: List[float]
    linear_fit_param: List[float]
    shutter_jitter: float
