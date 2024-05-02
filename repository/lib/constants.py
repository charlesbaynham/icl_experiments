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
from dataclasses import dataclass
from typing import Optional

from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam


USE_SR87 = True
"Are we using strontium-87 or strontium-88 at the moment? For now, we simply alter this constant and recommit the code to swap isotopes"

USE_LATTICE_OFFSETS = False
"Are we trying to load a lattice or just make a MOT? TODO: This should not be in this file."

URUKULED_BEAMS = [
    UrukuledBeam(
        name="red_doublepass_injection",
        frequency=365.0e6,
        amplitude=1.0,
        attenuation=0.0,
        urukul_device="urukul9910_aom_doublepass_689_red_injection",
    ),
    UrukuledBeam(
        name="blue_doublepass_injection",
        frequency=200.0e6,
        amplitude=1.0,
        attenuation=20.0,
        urukul_device="urukul9910_aom_doublepass_461_injection",
    ),
    UrukuledBeam(
        name="red_spinpol",
        frequency=366.6e6,
        amplitude=1.0,
        attenuation=0.0,
        urukul_device="urukul9910_aom_doublepass_689_spinpol",
    ),
    UrukuledBeam(
        name="clock_up",
        frequency=200e6,
        attenuation=0,
        urukul_device="urukul9912_aom_698_up_switch",
    ),
    UrukuledBeam(
        "blue_imaging_switch",
        frequency=100e6,
        attenuation=13,
        urukul_device="urukul9912_aom_singlepass_461_imaging_switch",
    ),
]
"Urukul outputs (name, freq, amplitude, attenuation) required for non-suservo ad9910 aoms"

# Convert to dict for ease of use
URUKULED_BEAMS = {beam.name: beam for beam in URUKULED_BEAMS}


RED_SPINPOL_SETTINGS = UrukuledBeam(  # TODO: Get rid of this once !31 is merged
    "red_spinpol",
    frequency=366.6e6,
    attenuation=0.0,
    amplitude=1.0,  # TODO: Remove this after pyaion update
    urukul_device="urukul9910_aom_doublepass_689_red_spinpol",
)


# Setpoints for the red sigmaplus and sigmaminus SUServos while running the spin
# polarizing beam (i.e. not their normal MOT beams)
RED_SPINPOL_SETPOINT_SIGMAPLUS = 1.5  # V
RED_SPINPOL_SETPOINT_SIGMAMINUS = 1.5  # V


# Lattice ramp-down configuration
# TODO: Choose real lattice ramp parameters
LATTICE_HIGH_SETPOINT_MULTIPLE = 1.0
LATTICE_LOW_SETPOINT_MULTIPLE = 0.1


@dataclass
class IJDSettings:
    temperature: float
    "Temperature / Ohms"
    window_high: float
    "Top end of window / A"
    window_low: float
    "Bottom end of window / A"
    relock_step: float
    "Current step to make above lockpoint for relocking / A"
    relock_waittime: float = 1.0
    "Time to wait between relock steps / s. Default = 1.0"
    associated_aom: Optional[str] = None
    "AOMs from AD9910_BEAMS required for IJD to lock"


IJD_DEFAULTS = {
    "blue_IJD1_controller": IJDSettings(
        8600, 360e-3, 350e-3, 3e-3, associated_aom="blue_doublepass_injection"
    ),
    "blue_IJD2_controller": IJDSettings(8800, 370.5e-3, 367e-3, 3e-3),
    "blue_IJD3_controller": IJDSettings(8850, 355e-3, 345e-3, 3e-3),
    "red_IJD1_controller": IJDSettings(
        9460, 189.0e-3, 186.0e-3, 3e-3, associated_aom="red_doublepass_injection"
    ),
}
"Injected diode default settings"


# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 1000),
        ("Height", 1000),
        ("OffsetX", 400),
        ("OffsetY", 500),
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

# Default field in chamber 1
B_FIELD_CH1_AXIAL = 0.0  # A

if USE_SR87 and USE_LATTICE_OFFSETS:
    # With 6A gradient
    B_FIELD_BIAS_X = 0.5  # A
    B_FIELD_BIAS_Y = -0.05  # A
    B_FIELD_BIAS_Z = (
        -1.6 - 0.29
    )  # A  # FIXME I've guessed the offset required here based on the current supply misconfiguration described in the onenote on 20240502
elif not USE_SR87 and USE_LATTICE_OFFSETS:
    # With 1A gradient
    B_FIELD_BIAS_X = 0.5  # A
    B_FIELD_BIAS_Y = -0.02  # A
    B_FIELD_BIAS_Z = -1.01  # A
else:
    # Default fields in chamber 2 for nulling field
    B_FIELD_BIAS_X = 0.3  # A
    B_FIELD_BIAS_Y = -0.014  # A
    B_FIELD_BIAS_Z = -1.04  # A

B_FIELD_GRADIENT = 90.0  # A


BLUE_LOADING_TIME = 500e-3
"Default blue MOT loading time"

RED_INJECTION_AOM_ATTENUATION = 0.0
"Default attenuation for the 689 injection AOM"

RED_INJECTION_AOM_FREQUENCY = 366.6e6  # TODO: Get rid of this once !31 is merged
"Nominal frequency for the 689 injection AOM"

RED_BROADBAND_RAMP_LIMIT = 4e6
"Ramp extent for the broadband red stage (n.b. will be double by the double-pass AOM)"

RED_INJECTION_AOM_RAMP_FREQUENCY = 30e3
"Default ramp frequency for the broadband red MOT"


RED_BROADBAND_TIME = 100e-3
"Default time in broadband red MOT"

DEFAULT_IMAGING_PULSE = 250e-6
"Default length of an imaging pulse of 461nm light. Usually overriden by purpose."


ANDOR_CAMERA_SHUTTER_OPEN_TIME = 130e-3  # Could probably be shorter if required
"Pre-open delay for the Andor camera's external protective shutter"

# The Andor camera has a sensor size of 512x512. These are only true for EM gain
# mode! It's different in conventional gain mode
x, y, width = 212, 222, 100
ANDOR_ROI_X0 = x - width / 2
ANDOR_ROI_X1 = x + width / 2
ANDOR_ROI_Y0 = y - width / 2
ANDOR_ROI_Y1 = y + width / 2

ANDOR_SENSOR_HEIGHT = 512
ANDOR_SENSOR_WIDTH = 512
ANDOR_FAST_KINETICS_HEIGHT = width

DEFAULT_CAMERA_EXPOSURE_TIME = 200e-6
"Camera exposure time, also used for length of fluorescence pulse by default"

SRS_SHUTTER_DELAY = 5e-3

# Information about beams controlled by AOMs
SUSERVOED_BEAMS = [
    ### BLUE ###
    SUServoedBeam(
        "blue_push_beam",
        150e6,
        20,
        "suservo_aom_singlepass_461_pushbeam",
        "TTL_shutter_461_pushbeam",
        shutter_delay=20e-3,
        setpoint=0.8,
        servo_enabled=True,
    ),
    SUServoedBeam(
        "blue_2dmot_A",
        120e6,
        21,
        "suservo_aom_singlepass_461_2dmot_a",
        "TTL_shutter_461_2dmot_is_it_a",
        shutter_delay=20e-3,
        setpoint=1.9,
        servo_enabled=True,
    ),
    SUServoedBeam(
        "blue_2dmot_B",
        120e6,
        21,
        "suservo_aom_singlepass_461_2dmot_b",
        "TTL_shutter_461_2dmot_is_it_b",
        shutter_delay=20e-3,
        setpoint=2.9,
        servo_enabled=True,
    ),
    SUServoedBeam(
        "blue_3dmot_radial",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_radial",
        "TTL_shutter_461_3dmot",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=2.8,
    ),
    SUServoedBeam(
        "blue_3dmot_axialminus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        "TTL_shutter_461_3dmot",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=3.0,
    ),
    SUServoedBeam(
        "blue_3dmot_axialplus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=2.0,
    ),
    SUServoedBeam(
        "blue_imaging_delivery",
        116e6,
        22,
        "suservo_aom_singlepass_461_imaging_delivery",
        servo_enabled=True,
        setpoint=2.0,
    ),
    ### RED ###
    SUServoedBeam(
        "red_mot_diagonal",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_diagonal",
        shutter_device="ttl_shutter_red_mot_diagonal",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=1.5,
        photodiode_offset=0.01326,
    ),
    SUServoedBeam(
        "red_mot_sigmaminus",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaminus",
        shutter_device="ttl_shutter_red_sigmaminus",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=1.5,
        photodiode_offset=0.0188,
    ),
    SUServoedBeam(
        "red_up",
        100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_up",
        shutter_device="ttl_shutter_red_up",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=1.1,  # Chosen based on measured 1.4V at max power on 2024/02/26 (i.e. not carefully)
        photodiode_offset=0.0188,  # TODO: This is a guess
    ),
    SUServoedBeam(
        "red_mot_sigmaplus",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaplus",
        shutter_device="ttl_shutter_red_sigmaplus",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=1.5 if not USE_SR87 else 3.0,  # 3 V for Sr87
        photodiode_offset=0.0188,  # TODO: This is a guess
    ),
    ### OTHER ###
    SUServoedBeam(
        "repump_707",
        100e6,
        0,
        "suservo_aom_singlepass_707",
        shutter_device="ttl_shutter_repump_707",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=0.75,
    ),
    SUServoedBeam(
        "repump_679",
        100e6,
        0,
        "suservo_aom_singlepass_679",
        shutter_device="ttl_shutter_repump_679",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=0.33,
    ),
    SUServoedBeam(
        "lattice_input_1379",
        frequency=80e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_1379_cavity_input",
        servo_enabled=True,
        setpoint=5.5,
    ),
]

# Convert to dict for ease of use
SUSERVOED_BEAMS = {beam.name: beam for beam in SUSERVOED_BEAMS}


# Mirny settings for Sr 88 / Sr 87
@dataclass
class MirnySettings:
    device_name: str
    frequency: float
    attenuation: float = 30.0
    rf_switch: bool = True


MIRNY_SETTINGS_88 = [
    MirnySettings(
        device_name="mirny_eom_cavity_offset_689",
        frequency=583e6,
        attenuation=7.0,
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_A", frequency=100e6, rf_switch=False
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_B", frequency=100e6, rf_switch=False
    ),
    MirnySettings(
        device_name="mirny_eom_689_sideband", frequency=100e6, rf_switch=False
    ),
]

MIRNY_SETTINGS_87 = [
    MirnySettings(
        device_name="mirny_eom_cavity_offset_689",
        frequency=660.3e6,
        attenuation=4.0,
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_A", frequency=576e6, attenuation=20.0
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_B", frequency=487e6, attenuation=24.0
    ),
    MirnySettings(
        device_name="mirny_eom_689_sideband", frequency=1463.265e6, attenuation=20.0
    ),
]

assert [s.device_name for s in MIRNY_SETTINGS_87] == [
    s.device_name for s in MIRNY_SETTINGS_88
], "Please ensure both lists are in the same order"


# WAND defaults for the two isotopes
# Lasers not listed will be ignored. Lasers set to NaN will have their locks disabled
WAND_OFFSETS_88 = {"461": -20e6, "707": 0, "679": 0, "689": float("nan")}
WAND_OFFSETS_87 = {
    "461": -75e6,
    "707": +15e6,
    "679": -2430e6,
    "689": float("nan"),
}

# Spin polarisation settings

TIME_IN_LATTICE_BEFORE_SPIN_POL = 5e-3
DURATION_OF_SPIN_POL = 20e-3
TIME_IN_LATTICE_AFTER_SPIN_POL = 0e-3
