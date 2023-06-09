"""
Experimental constants
======================

This module is used to store static constants that can be referred to by other
parts of the code. This is the only file where magic numbers should be stored,
so you should never e.g. store an AOM's optimal attenuation as a default setting
in a build() method somewhere: it should be here.

This file should (ideally) not be used to store hardware state - see
:mod:`device_db_config.configuration` for that.

If it makes sense to have hardware and experimental constants stored together
(e.g. for the :class:`~pyaion.models.SUServoedBeam` objects below) then prefer
this module.
"""
from collections import OrderedDict

from pyaion.models import SUServoedBeam

# Injected diode default temperatures and window positions

IJD_DEFAULTS = {
    "blue_IJD1_controller": (8500, 345e-3),
    "blue_IJD2_controller": (8800, 345e-3),
    "blue_IJD3_controller": (9000, 346e-3),
}

# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 584),
        ("Height", 726),
        ("OffsetX", 944),
        ("OffsetY", 584),
    ]
)
"Chamber 2 horizontal camera settings. Must be valid Features (see http://softwareservices.flir.com/BFS-PGE-50S5/latest/Model/public/index.html)"

# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_VERTICAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 500),
        ("Height", 600),
        ("OffsetX", 972),
        ("OffsetY", 878),
    ]
)
"Chamber 2 vertical camera settings. Must be valid Features (see http://softwareservices.flir.com/BFS-PGE-50S5/latest/Model/public/index.html)"


# Default field in chamber 2
B_FIELD_BIAS_X = 0.0  # A
B_FIELD_BIAS_Y = 0.0  # A
B_FIELD_BIAS_Z = 0.0  # A
B_FIELD_GRADIENT = 100.0  # A

RED_INJECTION_AOM_ATTENUATION = 0
"Default attenuation for the 689 injection AOM"

RED_INJECTION_AOM_FREQUENCY = 200e6
"Default frequency for the 689 injection AOM"

# Information about beams controlled by AOMs
AOM_BEAMS = [
    ### BLUE ###
    SUServoedBeam(
        "blue_push_beam",
        150e6,
        20,
        "suservo_aom_singlepass_461_pushbeam",
        "TTL_shutter_461_pushbeam",
        shutter_delay=20e-3,
    ),
    SUServoedBeam(
        "blue_2dmot_A",
        100e6,
        20,
        "suservo_aom_singlepass_461_2dmot_a",
        "TTL_shutter_461_2dmot_is_it_a",
        shutter_delay=20e-3,
    ),
    SUServoedBeam(
        "blue_2dmot_B",
        100e6,
        20,
        "suservo_aom_singlepass_461_2dmot_b",
        "TTL_shutter_461_2dmot_is_it_b",
        shutter_delay=20e-3,
    ),
    SUServoedBeam(
        "blue_3dmot_radial",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_radial",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
    ),
    SUServoedBeam(
        "blue_3dmot_axialplus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
    ),
    SUServoedBeam(
        "blue_3dmot_axialminus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
    ),
    SUServoedBeam(
        "blue_injection",
        200e6,
        24,
        "suservo_aom_doublepass_461_injection",
    ),
    SUServoedBeam(
        "blue_spectroscopy",
        200e6,
        20,
        "suservo_aom_singlepass_461_spectroscopy",
    ),
    ### RED ###
    SUServoedBeam(
        "red_MOT_diag",
        200e6,
        0,
        "suservo_aom_singlepass_689_redMOT_diag",
    ),
    SUServoedBeam(
        "red_up",
        200e6,
        0,
        "suservo_aom_singlepass_689_up",
    ),
    SUServoedBeam(
        "red_MOT_axialplus",
        200e6,
        0,
        "suservo_aom_singlepass_689_redMOT_axialplus",
    ),
    SUServoedBeam(
        "red_MOT_axialminus",
        200e6,
        0,
        "suservo_aom_singlepass_689_redMOT_axialminus",
    ),
    ### OTHER ###
    SUServoedBeam(
        "repump_707",
        200e6,
        20,
        "suservo_aom_singlepass_707",
    ),
    SUServoedBeam(
        "repump_679",
        200e6,
        20,
        "suservo_aom_singlepass_679",
    ),
]

# Convert to dict for ease of use
AOM_BEAMS = {beam.name: beam for beam in AOM_BEAMS}
