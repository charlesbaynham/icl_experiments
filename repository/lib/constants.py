"""Constants

This module is simply used to store static constants that can be referred to
by other parts of the code. This is the only file where magic numbers should
be stored, so you should never e.g. store an AOM's optimal attenuation as a
default setting in a build() method somewhere: it should be here.
"""
from dataclasses import dataclass
from typing import Optional

# IJD1

IJD1_TEMPERATURE = 9632  # Ohms

# Information about beams controlled by AOMs
@dataclass
class SUServoedBeam:
    frequency: float
    attenuation: float
    suservo_device: str
    shutter_device: str = Optional[None]
    shutter_delay: float = 0.0


AOM_BEAMS = {
    "blue_push_beam": SUServoedBeam(
        150e6, 20, "suservo_aom_singlepass_461_pushbeam", "TTL_shutter_461_pushbeam"
    ),
    "blue_2dmot_A": SUServoedBeam(
        100e6, 20, "suservo_aom_singlepass_461_2dmot_a", "TTL_shutter_461_2dmot_is_it_a"
    ),
    "blue_2dmot_B": SUServoedBeam(
        100e6, 20, "suservo_aom_singlepass_461_2dmot_b", "TTL_shutter_461_2dmot_is_it_b"
    ),
    "blue_3dmot_radial": SUServoedBeam(
        150e6, 20, "suservo_aom_singlepass_461_3DMOT_radial", "TTL_shutter_461_3dmot"
    ),
    "blue_3dmot_axialplus": SUServoedBeam(
        150e6, 20, "suservo_aom_singlepass_461_3DMOT_axialplus", "TTL_shutter_461_3dmot"
    ),
    "blue_3dmot_axialminus": SUServoedBeam(
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        "TTL_shutter_461_3dmot",
    ),
    "blue_injection": SUServoedBeam(200e6, 24, "suservo_aom_doublepass_461_injection"),
    "blue_spectroscopy": SUServoedBeam(
        200e6, 20, "suservo_aom_singlepass_461_spectroscopy"
    ),
}
