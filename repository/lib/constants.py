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


SR_FACTS = {
    "FREQUENCIES": {
        "689_88": 434829121311e3,  # 10.1103/PhysRevLett.91.243002
        "689_88_1s": 10e3,  # 10.1103/PhysRevLett.91.243002
    }
}


USE_SR87 = True
"Are we using strontium-87 or strontium-88 at the moment? For now, we simply alter this constant and recommit the code to swap isotopes"

USE_LATTICE_MODE = False
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
        "red_spinpol",
        frequency=366.6e6,
        amplitude=1.0,
        attenuation=0.0,
        urukul_device="urukul9910_aom_doublepass_689_red_spinpol",
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
        ("OffsetY", 920),
    ]
)
"Chamber 2 vertical camera settings. Must be valid Features (see http://softwareservices.flir.com/BFS-PGE-50S5/latest/Model/public/index.html)"

# Default field in chamber 1
B_FIELD_CH1_AXIAL = 0.0  # A

if USE_SR87 and USE_LATTICE_MODE:
    # With 6A gradient
    B_FIELD_BIAS_X = 1.1  # A
    B_FIELD_BIAS_Y = -0.02  # A
    B_FIELD_BIAS_Z = -1.4  # A
elif not USE_SR87 and USE_LATTICE_MODE:
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


RED_BROADBAND_RAMP_LIMIT = 4e6
"Ramp extent for the broadband red stage (n.b. will be double by the double-pass AOM)"

RED_INJECTION_AOM_RAMP_FREQUENCY = 30e3
"Default ramp frequency for the broadband red MOT"


RED_BROADBAND_TIME = 100e-3
"Default time in broadband red MOT"

RED_MOT_FINAL_HOLD_TIME = 0 if USE_SR87 else 100e-3
"Default final hold time in last stage of the red mot"

DEFAULT_IMAGING_PULSE = 50e-6
"Default length of an imaging pulse of 461nm light. Usually overriden by purpose."


ANDOR_CAMERA_SHUTTER_OPEN_TIME = 130e-3  # Could probably be shorter if required
"Pre-open delay for the Andor camera's external protective shutter"

ANDOR_CAMERA_TRIGGER_ENABLE_TIME = 1e-6
"Trigger the ANDOR camera this much before the actual requested trigger point"

ANDOR_CAMERA_BACKGROUND_DELAY = 60e-3
"Delay before background image when using the Andor for background-corrected images"

# The Andor camera has a sensor size of 512x512. These are only true for EM gain
# mode! It's different in conventional gain mode
x, y, width, height = 230, 285, 100, 100

if USE_LATTICE_MODE:
    ANDOR_ROI_X0 = 50
    ANDOR_ROI_X1 = 300
    ANDOR_ROI_Y0 = 280
    ANDOR_ROI_Y1 = 320

else:
    ANDOR_ROI_X0 = x - width / 2
    ANDOR_ROI_X1 = x + width / 2
    ANDOR_ROI_Y0 = y - height / 2
    ANDOR_ROI_Y1 = y + height / 2

ANDOR_SENSOR_HEIGHT = 512
ANDOR_SENSOR_WIDTH = 512
ANDOR_FAST_KINETICS_HEIGHT = height

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
        initial_amplitude=0.05,
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
        initial_amplitude=0.05,
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
        initial_amplitude=0.05,
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
        initial_amplitude=0.05,
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


# These frequencies were chosen empirically based on the atoms
_default_461 = 650504048e6
_default_707 = 423913481e6
_default_679 = 441332637e6
_default_698 = 429228355e6

# Calibrated empirically - I know it's not right but we seem to optimize here
# for some reason
_isotope_shift_689 = 1241e6

# The Wavemeter is calibrated relative to the Sr 88 689nm transition, so we use
# the absolute frequency and the value of the AOMs between the wavemeter pickoff
# and the atoms as a calibration
_default_689 = (
    SR_FACTS["FREQUENCIES"]["689_88"]
    + 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency
    + SUSERVOED_BEAMS["red_mot_diagonal"].frequency
)


MIRNY_SETTINGS_88 = [
    MirnySettings(
        device_name="mirny_eom_cavity_offset_689",
        frequency=580.7e6,
        attenuation=3.0,
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
        frequency=_isotope_shift_689 - MIRNY_SETTINGS_88[0].frequency,
        attenuation=5.0,
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

# WAND frequency references and lock settings for the two isotopes. Lasers not
# listed will be ignored. Entries are a tuple of (reference, locked): the laser
# frequency will be set to "reference" and the lock will be enabled / disabled
# according to "locked"
WAND_SETPOINTS_88 = {
    "461": (_default_461 - 10e6, True),
    "707": (_default_707, True),
    "679": (_default_679, True),
    "689": (_default_689, False),
    "689_IJD": (
        _default_689 - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    "698": (_default_698, False),
}


WAND_SETPOINTS_87 = {
    "461": (_default_461 - 55e6, True),
    "707": (_default_707 + 27e6, True),
    "679": (_default_679 - 2430e6, True),
    "689": (_default_689 - _isotope_shift_689, False),
    "689_IJD": (
        _default_689
        - _isotope_shift_689
        - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    "698": (_default_698, False),
}

# Spin polarisation settings

TIME_IN_LATTICE_BEFORE_SPIN_POL = 5e-3
DURATION_OF_SPIN_POL = 20e-3
TIME_IN_LATTICE_AFTER_SPIN_POL = 0e-3
