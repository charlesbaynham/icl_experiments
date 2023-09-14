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

from repository.lib.models import SUServoedBeam

# from pyaion.models import SUServoedBeam # FIXME


IJD_AOMS = {
    "red_IJD1_controller": ("urukul9910_aom_doublepass_689_red_injection", 340.0e6, 0.0)
}
"Urukul outputs (name, freq, attenuation) required for injection locks"

IJD_DEFAULTS = {
    "blue_IJD1_controller": (8500, 350e-3, 343e-3),
    "blue_IJD2_controller": (8800, 350e-3, 343e-3),
    "blue_IJD3_controller": (9000, 350e-3, 343e-3),
    "red_IJD1_controller": (6300, 71.0e-3, 67.0e-3),
}
"Injected diode default temperatures and window scan ranges"

# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 256),
        ("Height", 256),
        ("OffsetX", 1172),
        ("OffsetY", 790),
    ]
)
"Chamber 2 horizontal camera settings. Must be valid Features (see http://softwareservices.flir.com/BFS-PGE-50S5/latest/Model/public/index.html)"

# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_VERTICAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 256),
        ("Height", 256),
        ("OffsetX", 1368),
        ("OffsetY", 820),
    ]
)
"Chamber 2 vertical camera settings. Must be valid Features (see http://softwareservices.flir.com/BFS-PGE-50S5/latest/Model/public/index.html)"


# Default field in chamber 2
B_FIELD_BIAS_X = 0.1  # A
B_FIELD_BIAS_Y = -0.025  # A
B_FIELD_BIAS_Z = -0.68  # A
B_FIELD_GRADIENT = 100.0  # A


BLUE_LOADING_TIME = 500e-3
"Default blue MOT loading time"

RED_INJECTION_AOM_ATTENUATION = 0.0
"Default attenuation for the 689 injection AOM"

RED_INJECTION_AOM_FREQUENCY = 340e6
"Nominal frequency for the 689 injection AOM"

RED_INJECTION_AOM_RAMP_FREQUENCY = 30e3
"Default ramp frequency for the broadband red MOT"

RED_BROADBAND_CURRENT = 3.0
"Default current for broadband red MOT"

RED_BROADBAND_TIME = 100e-3
"Default time in broadband red MOT"

OFFSET_FREQUENCY_689 = 553e6
"""
Default cavity offset frequency for the 689's laser stabilization

Note - this is currently (2023-08-02) unused since the EOM is driven statically by a RIGOL
"""

OFFSET_ATTENUATION_689 = 7.0
"Default cavity offset attenuation for the 689's laser stabilization"

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
        setpoint=1.5,
        servo_enabled=True,
    ),
    SUServoedBeam(
        "blue_2dmot_B",
        100e6,
        20,
        "suservo_aom_singlepass_461_2dmot_b",
        "TTL_shutter_461_2dmot_is_it_b",
        shutter_delay=20e-3,
        setpoint=1.5,
        servo_enabled=True,
    ),
    SUServoedBeam(
        "blue_3dmot_radial",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_radial",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=3.5,
    ),
    SUServoedBeam(
        "blue_3dmot_axialplus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=5.0,
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
    # SUServoedBeam(
    #     "blue_spectroscopy",
    #     200e6,
    #     20,
    #     "suservo_aom_singlepass_461_spectroscopy",
    # ),
    ### RED ###
    SUServoedBeam(
        "red_mot_diagonal",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_diagonal",
        shutter_device="ttl_shutter_red_mot_diagonal",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=2.0,
        photodiode_offset=0.01326,
    ),
    SUServoedBeam(
        "red_mot_sigmaminus",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaminus",
        shutter_device="ttl_shutter_red_sigmaminus",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=2.5,
        photodiode_offset=0.0188,
    ),
    # These beams are not currently installed:
    SUServoedBeam(
        "red_up",
        100e6,
        attenuation=30,  # This beam is not currently used - turn it off here to avoid confusion
        suservo_device="suservo_aom_singlepass_689_up",
        shutter_device="ttl_shutter_red_up",
        shutter_delay=10e-3,
    ),
    SUServoedBeam(
        "red_mot_sigmaplus",
        100e6,
        attenuation=30,  # This beam is not currently used - turn it off here to avoid confusion
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaplus",
        shutter_device="ttl_shutter_red_sigmaplus",
        shutter_delay=10e-3,
    ),
    ### OTHER ###
    SUServoedBeam(
        "repump_707",
        100e6,
        0,
        "suservo_aom_singlepass_707",
        shutter_device="ttl_shutter_repump_707",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=0.75,
    ),
    SUServoedBeam(
        "repump_679",
        100e6,
        0,
        "suservo_aom_singlepass_679",
        shutter_device="ttl_shutter_repump_679",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=0.33,
    ),
]

# Convert to dict for ease of use
AOM_BEAMS = {beam.name: beam for beam in AOM_BEAMS}
