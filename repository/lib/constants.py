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
from dataclasses import field
from typing import Optional

from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

SR_FACTS = {
    "FREQUENCIES": {
        "689_88": 434829121311e3,  # 10.1103/PhysRevLett.91.243002
        "689_88_1s": 10e3,  # 10.1103/PhysRevLett.91.243002
    }
}


USE_SR87 = False
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
    UrukuledBeam(
        "blue_USOC_delivery",
        frequency=100e6,
        attenuation=15,
        urukul_device="urukul9910_aom_doublepass_461_USOC_delivery",
    ),
    UrukuledBeam(
        "dipole_trap_1064_freespace_AOM",
        frequency=110e6,
        attenuation=3.0,
        urukul_device="urukul_aom_1064_switch",
    ),
]
"Urukul outputs (name, freq, amplitude, attenuation) required for non-suservo ad9910 aoms"

# Convert to dict for ease of use
URUKULED_BEAMS = {beam.name: beam for beam in URUKULED_BEAMS}


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
    associated_beams: list = field(default_factory=lambda: [])
    "Beams from AD9910_BEAMS required for IJD to lock"


IJD_DEFAULTS = {
    "blue_IJD1_controller": IJDSettings(
        8600,
        360e-3,
        350e-3,
        3e-3,
        associated_beams=["blue_doublepass_injection", "blue_USOC_delivery"],
    ),
    "blue_IJD2_controller": IJDSettings(
        8800,
        373e-3,
        367e-3,
        3e-3,
    ),
    "blue_IJD3_controller": IJDSettings(8850, 360e-3, 350e-3, 3e-3),
    "red_IJD1_controller": IJDSettings(
        9460, 191.0e-3, 188.0e-3, 3e-3, associated_beams=["red_doublepass_injection"]
    ),
}
"Injected diode default settings"

RED_IJD_RELOCK_FREQUENCY_BOOST = 2e6
"Amount to increase red AOM frequency from default while relocking the IJD"


@dataclass
class IJDRelockerSettings:
    board_name: str
    "Name of relocker board in device_db"
    channel: int
    "Channel on relocker board"
    v_min: float
    "Lowest voltage/end of scan"
    v_max: float
    "Highest voltage/start of scan"
    n_steps: float
    "Number of scan steps. cannot be >100"

    window_frac: float
    "Fraction of the way along the detected window to set the lock point"
    min_diff: float
    "Minimum acceptable size of jump on steep side of window"
    v_low_threshold: float
    "Maximum allowed value for the lowest read voltage for relocking to take place"
    v_rise_threshold: float
    "Voltage increase on shallow side of the window"
    wait_time: float
    "Time to settle before setting lock voltage"

    auto_relock: bool
    "Turn on auto relocking or not"

    associated_controller: Optional[str] = None
    "Koheron controller associated with the channel"

    def __post_init__(self):
        if self.n_steps > 100:
            self.n_steps = 100


IJD_RELOCKER_DEFAULTS = {
    "blue_IJD1_relocker": IJDRelockerSettings(
        "blue_relocker",
        0,
        -2,
        2,
        100,
        0.6,
        0.1,
        1.4,
        0.05,
        1000,
        True,
        "blue_IJD1_controller",
    ),
    "blue_IJD2_relocker": IJDRelockerSettings(
        "blue_relocker",
        1,
        -2,
        2,
        100,
        0.6,
        0.1,
        1.4,
        0.05,
        1000,
        True,
        "blue_IJD2_controller",
    ),
    "blue_IJD3_relocker": IJDRelockerSettings(
        "blue_relocker",
        2,
        -2,
        2,
        100,
        0.6,
        0.1,
        1.4,
        0.05,
        1000,
        True,
        "blue_IJD3_controller",
    ),
    "red_IJD1_relocker": IJDRelockerSettings(
        "red_relocker",
        0,
        -2,
        2,
        100,
        0.5,
        0.1,
        1.15,
        0.05,
        1000,
        True,
        "red_IJD1_controller",
    ),
}
"Settings for IJD relocker board channels"

FLIR_CAMERA_TRIGGER_PREEMPT_TIME = 30e-6
# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 8),
        ("Height", 8),
        ("OffsetX", 0),
        ("OffsetY", 0),
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

# TODO: Include FIELD_COMP as an offset to the other default fields below.
# Measure the FIELD_COMP required for zero field using Zeeman spectroscopy
FIELD_COMP_X = 0.3
FIELD_COMP_Y = -0.005
FIELD_COMP_Z = -0.75
FIELD_COMP = [FIELD_COMP_X, FIELD_COMP_Y, FIELD_COMP_Z]

if USE_SR87:
    # With 6A gradient
    B_FIELD_BIAS_LATTICE_X = 1.1  # A
    B_FIELD_BIAS_LATTICE_Y = -0.02  # A
    B_FIELD_BIAS_LATTICE_Z = -1.4  # A
else:
    # With 1A gradient
    B_FIELD_BIAS_LATTICE_X = 0.5  # A
    B_FIELD_BIAS_LATTICE_Y = -0.02  # A
    B_FIELD_BIAS_LATTICE_Z = -1.01  # A

# Default fields in chamber 2 for nulling field
B_FIELD_BIAS_MOT_X = 0.3  # A
B_FIELD_BIAS_MOT_Y = -0.014  # A

if USE_SR87:
    B_FIELD_BIAS_MOT_Z = (
        -0.8
    )  # Sr87 prefers a bit of a bias field in the MOT. We should investigate
else:
    B_FIELD_BIAS_MOT_Z = -0.8


# Legacy naming.
B_FIELD_BIAS_X, B_FIELD_BIAS_Y, B_FIELD_BIAS_Z = (
    B_FIELD_BIAS_MOT_X,
    B_FIELD_BIAS_MOT_Y,
    B_FIELD_BIAS_MOT_Z,
)


# Use the lattice bias fields if the bodgy USE_LATTICE variable is set
# TODO: Get rid of this once we're shifting lattices
if USE_LATTICE_MODE:
    B_FIELD_BIAS_X, B_FIELD_BIAS_Y, B_FIELD_BIAS_Z = (
        B_FIELD_BIAS_LATTICE_X,
        B_FIELD_BIAS_LATTICE_Y,
        B_FIELD_BIAS_LATTICE_Z,
    )

B_FIELD_GRADIENT = 90.0  # A


BLUE_LOADING_TIME = 500e-3
"Default blue MOT loading time"


RED_BROADBAND_RAMP_LIMIT = 4e6
"Ramp extent for the broadband red stage (n.b. will be double by the double-pass AOM)"

RED_INJECTION_AOM_RAMP_FREQUENCY = 30e3
"Default ramp frequency for the broadband red MOT"


RED_MOT_FINAL_HOLD_TIME = 6e-3 if USE_SR87 else 100e-3
"Default final hold time in last stage of the red mot"

DEFAULT_IMAGING_PULSE = 50e-6
"Default length of an imaging pulse of 461nm light. Usually overriden by purpose."

DEFAULT_DELIVERY_SETTLING_DURATION = 100e-6
"Default duration of the delay between turning on the delivery AOM and turning on the fluoresence probe."

DEFAULT_IMAGING_DELIVERY_SUSERVO_PID_I = -200000
"$k_I$ constant for the flourescence beam's SUServo loop"

ANDOR_CAMERA_SHUTTER_OPEN_TIME = 130e-3  # Could probably be shorter if required
"Pre-open delay for the Andor camera's external protective shutter"

ANDOR_CAMERA_TRIGGER_ENABLE_TIME = 1e-6
"Trigger the ANDOR camera this much before the actual requested trigger point"

ANDOR_CAMERA_BACKGROUND_DELAY = 60e-3
"Delay before background image when using the Andor for background-corrected images"

# The Andor camera has a sensor size of 512x512. These are only true for EM gain
# mode! It's different in conventional gain mode
x, y, width, height = 205, 290, 100, 100

if USE_LATTICE_MODE:
    ANDOR_ROI_X0 = 50
    ANDOR_ROI_X1 = 300
    ANDOR_ROI_Y0 = 280
    ANDOR_ROI_Y1 = 320

else:
    if USE_SR87:
        ANDOR_ROI_X0 = 150
        ANDOR_ROI_X1 = 350
        ANDOR_ROI_Y0 = 285
        ANDOR_ROI_Y1 = 331
    else:
        ANDOR_ROI_X0 = x - width / 2
        ANDOR_ROI_X1 = x + width / 2
        ANDOR_ROI_Y0 = y - height / 2
        ANDOR_ROI_Y1 = y + height / 2

ANDOR_SENSOR_HEIGHT = 512
ANDOR_SENSOR_WIDTH = 512
ANDOR_FAST_KINETICS_HEIGHT = 170


# %% 689 spectroscopy defaults

ANDOR_689_FAST_KINETICS_X0 = 52
ANDOR_689_FAST_KINETICS_X1 = 160
FLUORESCENCE_PULSE_DURATION_689 = 4e-6


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
        attenuation=20,
        initial_amplitude=0.05,
        suservo_device="suservo_aom_singlepass_461_imaging_delivery",
        servo_enabled=True,
        setpoint=1.5,
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
        setpoint=0.4,
        initial_amplitude=0.05,
        photodiode_offset=0.017,
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
        "clock_delivery",
        100e6,
        9,
        "suservo_aom_698_clock_delivery",
        servo_enabled=True,
        setpoint=1.8,  # 270 mW in AOM 0th order with no diffraction
    ),
    SUServoedBeam(
        "lattice_input_1379",
        frequency=80e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_1379_cavity_input",
        servo_enabled=True,
        setpoint=5.5,
    ),
    SUServoedBeam(
        "down_813",
        frequency=180e6,
        attenuation=0.0,
        suservo_device="suservo_aom_down_813",
        servo_enabled=True,
        setpoint=3.5,
    ),
    SUServoedBeam(
        "up_813",
        frequency=90e6,
        attenuation=7.0,
        suservo_device="suservo_aom_up_813",
        servo_enabled=True,
        setpoint=3.5,
    ),
    SUServoedBeam(
        "dipole_trap_1064_delivery",
        frequency=110e6,
        attenuation=2.0,
        suservo_device="suservo_aom_1064_delivery",
        servo_enabled=True,
        setpoint=4.7,
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
_default_461 = 650504059e6
_default_707 = 423913478e6
_default_679 = 441332627e6
_default_698 = 429228355e6 + 358e6 + 180e6 - 522e6 + 16.3e6  # Measured empirically

# Calibrated empirically - I know it's not right but we seem to optimize here
# for some reason
_isotope_shift_689 = 1241.4e6

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
        device_name="mirny_eom_707_sideband_A", frequency=585e6, attenuation=20.0
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

WAND_1379_EXPOSURES = [
    200e-3,
    100e-3,
]
"Exposure settings for the wavemeter when it's measuring the doubled 1379 on the 689 path"

WAND_SHUTTERS_DELAY = 50e-3
"Shutter closing delay before WAND measurements of the 689 and 1379"

# WAND frequency references and lock settings for the two isotopes. Lasers not
# listed will be ignored. Entries are a tuple of (reference, locked): the laser
# frequency will be set to "reference" and the lock will be enabled / disabled
# according to "locked"
WAND_SETPOINTS_88 = {
    "461": (_default_461, True),
    "707": (_default_707, True),
    "679": (_default_679, True),
    "689": (_default_689, False),
    "689_IJD": (
        _default_689 - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    # "689_doubled1379": (_default_689, False),
    "698": (_default_698, False),
    "Sirah": (_default_698, False),
}


WAND_SETPOINTS_87 = {
    "461": (_default_461 - 60e6, True),
    "707": (_default_707 + 27e6, True),
    "679": (_default_679 - 2430e6, True),
    "689": (_default_689 - _isotope_shift_689, False),
    "689_IJD": (
        _default_689
        - _isotope_shift_689
        - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    # "689_doubled1379": (_default_689, False),
    "698": (_default_698, False),
    "Sirah": (_default_698, False),
}

# Spin polarisation settings

TIME_IN_LATTICE_BEFORE_SPIN_POL = 5e-3
DURATION_OF_SPIN_POL = 20e-3
TIME_IN_LATTICE_AFTER_SPIN_POL = 0e-3

# %% Dipole trap settings

DIPOLE_TRAP_HOLD_TIME = 200e-3
DIPOLE_TRAP_LOADING_TIME = 50e-3

DIPOLE_TRAP_MOLASSES_DURATION = 0.0
DIPOLE_TRAP_MOLASSES_DETUNING = 10e3
DIPOLE_TRAP_MOLASSES_SETPOINT_MULTIPLE = 0.05

# 3D blue transfer MOT settings

DELAY_INTO_RED_MOT_FOR_BLUE_BEAM_SWITCHOFF = 3e-3
BLUE_TRANSFER_MOT_DURATION = 4e-3
BLUE_TRANSFER_MOT_RAMP_TIMESTEP = 100e-6
BLUE_TRANSFER_MOT_GRADIENT_START = B_FIELD_GRADIENT
BLUE_TRANSFER_MOT_GRADIENT_END = 90.0
# Order: "suservo_aom_singlepass_461_3DMOT_axialminus","suservo_aom_singlepass_461_3DMOT_axialplus","suservo_aom_singlepass_461_3DMOT_radial"
BLUE_TRANSFER_MOT_SUSERVO_MULTIPLES_START = [1.0, 1.0, 1.0]
BLUE_TRANSFER_MOT_SUSERVO_MULTIPLES_END = [0.05, 0.05, 0.05]

# Red MOT phase parameters

# Order:
# "suservo_aom_singlepass_689_red_mot_sigmaplus",
# "suservo_aom_singlepass_689_red_mot_sigmaminus",
# "suservo_aom_singlepass_689_red_mot_diagonal",
# "suservo_aom_singlepass_689_up",

# Broadband phase
RED_BROADBAND_TIMESTEP = (
    20e-3  # TODO: fix this by changing the ordering of the camera shutter queueing
)
if USE_SR87:
    RED_BROADBAND_SUSERVO_MULTIPLES_START = [2.2, 2.2, 2.5, 0.5]
    RED_BROADBAND_SUSERVO_MULTIPLES_END = [2.2, 2.2, 2.5, 0.5]
    RED_BROADBAND_MOT_CURRENT_START = [6.0]
    RED_BROADBAND_MOT_CURRENT_END = [6.0]
    RED_BROADBAND_DURATION = 120e-3
else:
    RED_BROADBAND_SUSERVO_MULTIPLES_START = [2.2, 2.2, 2.5, 0.0]
    RED_BROADBAND_SUSERVO_MULTIPLES_END = [2.2, 2.2, 2.5, 0.0]
    RED_BROADBAND_MOT_CURRENT_START = [9.0]
    RED_BROADBAND_MOT_CURRENT_END = [9.0]
    RED_BROADBAND_DURATION = 100e-3

# Capture Phase (i.e. 1st narrowband red MOT)
RED_CAPTURE_DURATION = 10e-6
if USE_SR87:
    RED_CAPTURE_DETUNING_START = [0]
    RED_CAPTURE_DETUNING_END = [0]
    RED_CAPTURE_SUSERVO_MULTIPLES_START = [0.3, 0.3, 0.3, 0.5]
    RED_CAPTURE_SUSERVO_MULTIPLES_END = [0.1, 0.1, 0.1, 0.25]
    RED_CAPTURE_MOT_CURRENT_START = [6.0]
    RED_CAPTURE_MOT_CURRENT_END = [2.0]
else:
    RED_CAPTURE_DETUNING_START = [150e3]
    RED_CAPTURE_DETUNING_END = [50e3]
    RED_CAPTURE_SUSERVO_MULTIPLES_START = [0.55, 0.35, 0.6, 0.0]
    RED_CAPTURE_SUSERVO_MULTIPLES_END = [0.1, 0.1, 0.1, 0.0]
    RED_CAPTURE_MOT_CURRENT_START = [3.0]
    RED_CAPTURE_MOT_CURRENT_END = [1.0]


# Compression Phase (i.e. 2nd and final stage of narrowband red MOT)
RED_COMPRESSION_DURATION = 100e-3
if USE_SR87:
    RED_COMPRESSION_DETUNING_START = [100e3]
    RED_COMPRESSION_DETUNING_END = [0]
    RED_COMPRESSION_SUSERVO_MULTIPLES_START = [0.6, 0.6, 0.6, 1.5]
    RED_COMPRESSION_SUSERVO_MULTIPLES_END = [0.05, 0.05, 0.05, 0.2]
    RED_COMPRESSION_MOT_CURRENT_START = [2.0]
    RED_COMPRESSION_MOT_CURRENT_END = [2.0]
else:
    RED_COMPRESSION_DETUNING_START = [50e3]
    RED_COMPRESSION_DETUNING_END = [10e3]
    RED_COMPRESSION_SUSERVO_MULTIPLES_START = [0.1, 0.1, 0.1, 0.0]
    RED_COMPRESSION_SUSERVO_MULTIPLES_END = [0.02, 0.02, 0.02, 0.0]
    RED_COMPRESSION_MOT_CURRENT_START = [1.0]
    RED_COMPRESSION_MOT_CURRENT_END = [1.0]


### DIPOLE TRAP DEFAULT PARAMETERS ###

# Delay between end of red MOT and start of molasses
DELAY_BEFORE_MOLASSES = 10e-3
DELAY_BETWEEN_MOLASSES = 10e-3

XODT_MOLASSES_DURATION = 100e-3
# Order of suservos:
# "suservo_aom_singlepass_689_red_mot_sigmaplus",
# "suservo_aom_singlepass_689_red_mot_sigmaminus",
# "suservo_aom_singlepass_689_red_mot_diagonal",
# "suservo_aom_singlepass_689_up",
# "suservo_aom_1064_delivery",
# "suservo_aom_down_813"
XODT_MOLASSES_SETPOINT_MULTIPLES_START = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
XODT_MOLASSES_SETPOINT_MULTIPLES_END = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
# Urukul: "urukul9910_aom_doublepass_689_red_injection"
XODT_MOLASSES_689_DETUNING_START = [
    0e3,
]
XODT_MOLASSES_689_DETUNING_END = [
    0e3,
]
# Chamber 2 bias coils in amps. Order: X,Y,Z
XODT_MOLASSES_BIAS_FIELD_START = [a + b for a, b in zip(FIELD_COMP, [0.0, 0.0, 0.0])]
XODT_MOLASSES_BIAS_FIELD_END = [a + b for a, b in zip(FIELD_COMP, [0.0, 0.0, 0.0])]

XODT_2ND_MOLASSES_DURATION = 100e-3
XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_START = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_END = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
# Urukul: "urukul9910_aom_doublepass_689_red_injection"
XODT_2ND_MOLASSES_689_DETUNING_START = [
    0e3,
]
XODT_2ND_MOLASSES_689_DETUNING_END = [
    0e3,
]
# Chamber 2 bias coils in amps. Order: X,Y,Z
XODT_2ND_MOLASSES_BIAS_FIELD_START = [
    a + b for a, b in zip(FIELD_COMP, [0.0, 0.0, 0.0])
]
XODT_2ND_MOLASSES_BIAS_FIELD_END = [a + b for a, b in zip(FIELD_COMP, [0.0, 0.0, 0.0])]
