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

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

DELAY_BETWEEN_RTIO_EVENTS = 4e-9

SR_FACTS = {
    "FREQUENCIES": {
        "689_88": 434_829_121_311e3,  # 10.1103/PhysRevLett.91.243002
        "689_88_1s": 10e3,  # 10.1103/PhysRevLett.91.243002
    },
    "WAVELENGTHS": {"461_88": 460.86e-9},
}

ANDOR_CAMERA_FACTS = {"pixel_size": 16e-6, "magnification": 1}
ANDOR_CAMERA_FACTS["A_pixel"] = (
    ANDOR_CAMERA_FACTS["pixel_size"] / ANDOR_CAMERA_FACTS["magnification"]
) ** 2

GRAVITY_DOPPLER_PER_SEC_CLOCK = 429.229e12 * 9.81 / 3e8

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
        urukul_device="urukul9910_aom_doublepass_461_master_to_ijd1",
    ),
    UrukuledBeam(
        name="blue_singlepass_injection",
        frequency=120e6,
        amplitude=1.0,
        attenuation=21.0,
        urukul_device="urukul9910_aom_singlepass_461_ijd1_to_ijd23",
    ),
    UrukuledBeam(
        "red_spinpol",
        frequency=366.5e6,
        amplitude=1.0,
        attenuation=0.0,
        urukul_device="urukul9910_aom_doublepass_689_red_spinpol",
    ),
    UrukuledBeam(
        name="clock_up",
        frequency=200e6,
        attenuation=0.0,
        urukul_device="urukul9910_aom_698_up_switch",
    ),
    UrukuledBeam(
        name="clock_down",
        frequency=200e6,
        attenuation=0.0,
        urukul_device="urukul9910_aom_698_down_switch",
    ),
    UrukuledBeam(
        "blue_imaging_switch",
        frequency=100e6,
        attenuation=13,
        urukul_device="urukul9912_aom_singlepass_461_imaging_switch",
    ),
    # UrukuledBeam(  # On 20250603 this was not plugged in, it must have been like that for a while
    #     "blue_USOC_delivery",
    #     frequency=70e6,
    #     attenuation=20.0,
    #     urukul_device="urukul9910_aom_doublepass_461_USOC_delivery",
    # ),
    UrukuledBeam(
        "dipole_trap_1064_freespace_AOM",
        frequency=110e6,
        attenuation=3.0,
        urukul_device="urukul_aom_1064_switch",
    ),
    UrukuledBeam(
        "stark_shifter_689_switch",
        frequency=100e6,
        attenuation=9.0,
        urukul_device="urukul9912_aom_singlepass_689_stark_shifter_switch",
    ),
]
"Urukul outputs (name, freq, amplitude, attenuation) required for non-suservo ad9910 aoms"

# Convert to dict for ease of use
URUKULED_BEAMS = {beam.name: beam for beam in URUKULED_BEAMS}


# Setpoints for the red sigmaplus and sigmaminus SUServos while running the spin
# polarizing beam (i.e. not their normal MOT beams)
RED_SPINPOL_SETPOINT_SIGMAPLUS = 0.2  # V
RED_SPINPOL_SETPOINT_SIGMAMINUS = 0.2  # V
RED_SPINPOL_PGIA_GAIN = 0


RED_SPINPOL_RAMP_UPPER_LIMIT = 1.5e6
RED_SPINPOL_RAMP_LOWER_LIMIT = -1.5e6
"Ramp extent for the spin polarising beam (n.b. will be double by the double-pass AOM)"

RED_SPINPOL_AOM_RAMP_FREQUENCY = 30e3
"Default ramp frequency for the spin polarising beam"

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
    p_gain: float = 0.01
    "Proportional gain for the PID controller. Default = 0.01"
    i_gain: float = 0.00001
    "Integral gain for the PID controller. Default = 0.00001"
    d_gain: float = 0.0
    "Derivative gain for the PID controller. Default = 0.0"


IJD_DEFAULTS = {
    "blue_IJD1_controller": IJDSettings(
        temperature=8600,
        window_high=362e-3,
        window_low=352e-3,
        relock_step=3e-3,
        # IJD1 does not actually need the blue_singlepass_injection AOM, but
        # IJDs 2 and 3 do. Rather than adding it to one of IJD2 and 3, or both,
        # we add it here so there are no glitches during intialisation.
        associated_beams=["blue_doublepass_injection", "blue_singlepass_injection"],
    ),
    "blue_IJD2_controller": IJDSettings(
        temperature=8900,
        window_high=373e-3,
        window_low=368e-3,
        relock_step=3e-3,
    ),
    "blue_IJD3_controller": IJDSettings(
        temperature=8850,
        window_high=365e-3,
        window_low=355e-3,
        relock_step=3e-3,
    ),
    "red_IJD1_controller": IJDSettings(
        temperature=9380,
        window_high=174.0e-3,
        window_low=169.0e-3,
        relock_step=3e-3,
        associated_beams=["red_doublepass_injection"],
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
    "Lowest voltage/start of scan"
    v_max: float
    "Highest voltage/end of scan"
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
        board_name="blue_relocker",
        channel=0,
        v_min=-2,
        v_max=2,
        n_steps=100,
        window_frac=0.6,
        min_diff=0.1,
        v_low_threshold=1.45,
        v_rise_threshold=0.05,
        wait_time=1000,
        auto_relock=True,
        associated_controller="blue_IJD1_controller",
    ),
    "blue_IJD2_relocker": IJDRelockerSettings(
        board_name="blue_relocker",
        channel=1,
        v_min=-2,
        v_max=2,
        n_steps=100,
        window_frac=0.6,
        min_diff=0.1,
        v_low_threshold=1.4,
        v_rise_threshold=0.015,
        wait_time=1000,
        auto_relock=True,
        associated_controller="blue_IJD2_controller",
    ),
    "blue_IJD3_relocker": IJDRelockerSettings(
        board_name="blue_relocker",
        channel=2,
        v_min=-2,
        v_max=2,
        n_steps=100,
        window_frac=0.6,
        min_diff=0.1,
        v_low_threshold=1.36,
        v_rise_threshold=0.05,
        wait_time=1000,
        auto_relock=True,
        associated_controller="blue_IJD3_controller",
    ),
    "red_IJD1_relocker": IJDRelockerSettings(
        board_name="red_relocker",
        channel=0,
        v_min=-2,
        v_max=2,
        n_steps=100,
        window_frac=0.5,
        min_diff=0.1,
        v_low_threshold=1.15,
        v_rise_threshold=0.05,
        wait_time=1000,
        auto_relock=True,
        associated_controller="red_IJD1_controller",
    ),
}
"Settings for IJD relocker board channels"


@dataclass
class ScannerBoardSettings:
    board_name: str
    "Name of scanner board in device_db"
    channel: int
    "Channel on scanner board"
    v_min: float
    "Lowest voltage/start of scan"
    v_max: float
    "Highest voltage/end of scan"
    v_step: float
    "Voltage step size"
    freq: float
    "Frequency of the scan in Hz"


SCANNER_BOARD_DEFAULTS = {
    "filter_cavity_scanner": ScannerBoardSettings(
        "cavity_scanner",
        0,
        -2,
        2,
        0.01,
        100,
    ),
}

FLIR_CAMERA_TRIGGER_PREEMPT_TIME = 30e-6
# Order matters here since this is the order in which they are applied to the
# camera and it will complain if it's ever in an invalid state
CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS = OrderedDict(
    [
        ("Width", 256),
        ("Height", 256),
        ("OffsetX", 1700),
        ("OffsetY", 800),
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

DEFAULT_IMAGING_PULSE = 50e-6
"Default length of an imaging pulse of 461nm light. Usually overriden by purpose."

DEFAULT_DELIVERY_SETTLING_DURATION = 100e-6
"Default duration of the delay between turning on the delivery AOM and turning on the fluorescence probe."


ANDOR_CAMERA_SHUTTER_OPEN_TIME = 130e-3  # Could probably be shorter if required
"Pre-open delay for the Andor camera's external protective shutter"

ANDOR_CAMERA_TRIGGER_ENABLE_TIME = 1e-6
"Trigger the ANDOR camera this much before the actual requested trigger point"

ANDOR_CAMERA_BACKGROUND_DELAY = 60e-3
"Delay before background image when using the Andor for background-corrected images"

# The Andor camera has a sensor size of 512x512. These are only ROI definitions will
# only work in EM gain mode! The conventional gain readout has different X indices
# x, y, width, height = 215, 216, 100, 100

if USE_LATTICE_MODE:
    x, y, width, height = (
        215,
        216,
        100,
        100,
    )  # TODO: this needs to be done properly for lattice mode to match the below
    ANDOR_ROI_X0 = 50
    ANDOR_ROI_X1 = 300
    ANDOR_ROI_Y0 = 280
    ANDOR_ROI_Y1 = 320

else:
    if USE_SR87:
        x, y, width, height = 215, 273, 100, 100

    else:
        x, y, width, height = 215, 216, 100, 100

    ANDOR_ROI_X0 = x - width / 2
    ANDOR_ROI_X1 = x + width / 2
    ANDOR_ROI_Y0 = y - height / 2
    ANDOR_ROI_Y1 = y + height / 2

_ANDOR_ROI_DIPOLE_HEIGHT_ABOVE = 20
_ANDOR_ROI_DIPOLE_HEIGHT_BELOW = 20
_ANDOR_ROI_DIPOLE_WIDTH = 32

_ANDOR_DIPOLE_TRAP_BACKWARD_X = 193
# ~3 pixels below the center of the dipole trap to include falling atoms
_ANDOR_DIPOLE_TRAP_BACKWARD_Y = 245

_ANDOR_DIPOLE_TRAP_FORWARD_X = 196
# ~3 pixels below the center of the dipole trap to include falling atoms
_ANDOR_DIPOLE_TRAP_FORWARD_Y = 299

ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0 = round(
    _ANDOR_DIPOLE_TRAP_FORWARD_X - _ANDOR_ROI_DIPOLE_WIDTH / 2
)
ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1 = round(
    _ANDOR_DIPOLE_TRAP_FORWARD_X + _ANDOR_ROI_DIPOLE_WIDTH / 2
)
ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0 = round(
    _ANDOR_DIPOLE_TRAP_FORWARD_Y - _ANDOR_ROI_DIPOLE_HEIGHT_BELOW
)
ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1 = round(
    _ANDOR_DIPOLE_TRAP_FORWARD_Y + _ANDOR_ROI_DIPOLE_HEIGHT_ABOVE
)

ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0 = round(
    _ANDOR_DIPOLE_TRAP_BACKWARD_X - _ANDOR_ROI_DIPOLE_WIDTH / 2
)
ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1 = round(
    _ANDOR_DIPOLE_TRAP_BACKWARD_X + _ANDOR_ROI_DIPOLE_WIDTH / 2
)
ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0 = round(
    _ANDOR_DIPOLE_TRAP_BACKWARD_Y - _ANDOR_ROI_DIPOLE_HEIGHT_BELOW
)
ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1 = round(
    _ANDOR_DIPOLE_TRAP_BACKWARD_Y + _ANDOR_ROI_DIPOLE_HEIGHT_ABOVE
)

ANDOR_SENSOR_HEIGHT = 512
# ANDOR_SENSOR_WIDTH = 512

ANDOR_FAST_KINETICS_HEIGHT = height
ANDOR_FAST_KINETICS_OFFSET = round(y - height / 2)  # ANDOR_ROI_Y0

ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP = height
ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP = round(
    _ANDOR_DIPOLE_TRAP_FORWARD_Y - height / 2
)

SLACK_FOR_GRAVITY = 20
ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP = (
    2 * ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    + abs(_ANDOR_DIPOLE_TRAP_FORWARD_Y - _ANDOR_DIPOLE_TRAP_BACKWARD_Y)
)
ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP = (
    min(_ANDOR_DIPOLE_TRAP_FORWARD_Y, _ANDOR_DIPOLE_TRAP_BACKWARD_Y)
    - ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP / 2
    - SLACK_FOR_GRAVITY
)

# %% 689 spectroscopy defaults

ANDOR_689_FAST_KINETICS_X0 = 52
ANDOR_689_FAST_KINETICS_X1 = 160
FLUORESCENCE_PULSE_DURATION_689 = 4e-6


DEFAULT_CAMERA_EXPOSURE_TIME = 200e-6
"Camera exposure time, also used for length of fluorescence pulse by default"

SRS_SHUTTER_DELAY = 5e-3

SUSERVOED_BEAMS_LOW_INTENSITY = [
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
        photodiode_offset=0.0133,  # 0.001,  # 0.01238,
        pgia_setting=2,
        kI_loop_constant=-300.0,
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
        photodiode_offset=0.018,  # 0.001,
        pgia_setting=2,
        kI_loop_constant=-300.0,
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
        photodiode_offset=0.016,  # 0.0032,  # 0.016,
        pgia_setting=2,
        kI_loop_constant=-300.0,
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
        photodiode_offset=0.0131,  # 0.0027,  # 0.0108,
        pgia_setting=1,
        kI_loop_constant=-300.0,
    ),
]


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
        setpoint=2.9,
    ),
    SUServoedBeam(
        "blue_3dmot_axialplus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        setpoint=1.6,
    ),
    SUServoedBeam(
        "blue_imaging_delivery",
        116e6,
        attenuation=20,
        initial_amplitude=0.05,
        suservo_device="suservo_aom_singlepass_461_imaging_delivery",
        servo_enabled=True,
        setpoint=1.5,
        kI_loop_constant=-200000.0,
    ),
    SUServoedBeam(
        "blue_transparency_beam",
        80e6,
        20,
        "suservo_aom_singlepass_487_transparency",
        setpoint=0.3,
        servo_enabled=True,
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
        photodiode_offset=0.0133,  # 0.001,  # 0.01238,
    ),
    SUServoedBeam(
        "red_mot_sigmaminus",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaminus",
        shutter_device="ttl_shutter_red_sigmaminus",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        initial_amplitude=0.2,
        setpoint=1.5,
        photodiode_offset=0.018,  # 0.001,
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
        photodiode_offset=0.016,  # 0.0032,  # 0.016,
    ),
    SUServoedBeam(
        "red_mot_sigmaplus",
        frequency=100e6,
        attenuation=0.0,
        suservo_device="suservo_aom_singlepass_689_red_mot_sigmaplus",
        shutter_device="ttl_shutter_red_sigmaplus",
        shutter_delay=SRS_SHUTTER_DELAY,
        servo_enabled=True,
        initial_amplitude=0.2,
        setpoint=1.5 if not USE_SR87 else 3.0,  # 3 V for Sr87
        photodiode_offset=0.0131,  # 0.0027,  # 0.0108,
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
        setpoint=2.0,
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
        setpoint=3.5,
        kI_loop_constant=-100000.0,
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
        frequency=180e6 * 813 / 780,
        attenuation=0.0,
        suservo_device="suservo_aom_down_813",
        servo_enabled=True,
        initial_amplitude=0.0,
        setpoint=4.0,
        kI_loop_constant=-10000.0,
    ),
    SUServoedBeam(
        "up_813",
        frequency=90e6 * 813 / 780,
        attenuation=7.0,
        suservo_device="suservo_aom_up_813",
        servo_enabled=True,
        initial_amplitude=0.0,
        setpoint=3.5,
    ),
    SUServoedBeam(
        "dipole_trap_1064_delivery",
        frequency=110e6,
        attenuation=2.0,
        suservo_device="suservo_aom_1064_delivery",
        servo_enabled=True,
        initial_amplitude=0.0,
        setpoint=4.7,
        kI_loop_constant=-1000.0,
    ),
    SUServoedBeam(
        "stark_shifter_689_delivery",
        frequency=80e6,
        # Not maximum diffraction efficiency, but chosen so that we can't heat
        # the AOM too much. Achieves ~0.44V which is more than we need unless we move to very short pulses:
        attenuation=12.0,
        suservo_device="suservo_aom_singlepass_689_stark_shifter",
        servo_enabled=True,
        initial_amplitude=0.3,
        setpoint=0.28,  # Photodiode is now set to 30dB (changed 2024-12-02 from 20dB)
    ),
    SUServoedBeam(
        "down_689",
        frequency=80e6,  # TODO: Change back to 100 MHz before trying SWAP again
        attenuation=12.0,
        suservo_device="suservo_aom_singlepass_689_down_beam",
        servo_enabled=True,
        initial_amplitude=0.3,
        setpoint=0.28,
    ),
]

# Convert to dict for ease of use
SUSERVOED_BEAMS = {beam.name: beam for beam in SUSERVOED_BEAMS}
SUSERVOED_BEAMS_LOW_INTENSITY = {
    beam.name: beam for beam in SUSERVOED_BEAMS_LOW_INTENSITY
}


# Mirny settings for Sr 88 / Sr 87
@dataclass
class MirnySettings:
    device_name: str
    frequency: float
    attenuation: float = 30.0
    rf_switch: bool = True


# These frequencies were chosen empirically based on the atoms
_default_461 = (
    650_504_059e6
    # 2024-11-05
    + 10e6
    # 2024-11-18
    - 10e6
)
_default_707 = 423_913_478e6
_default_679 = 441_332_627e6
_default_487 = 615_103_493e6 + 25e9  # From NIST + blue detuning
_default_698 = 429_228_387.3e6  # Measured empirically
_clock_laser_offset = -80e6

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


MIRNY_SETTINGS_87 = [
    MirnySettings(
        device_name="mirny_eom_707_sideband_A", frequency=585e6, attenuation=20.0
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_B", frequency=487e6, attenuation=24.0
    ),
    MirnySettings(
        device_name="mirny_eom_689_sideband", frequency=1463.265e6, attenuation=20.0
    ),
    MirnySettings(
        device_name="mirny_eom_transfer_cavity_offset",
        frequency=2000e6,
        attenuation=20.0,
    ),
]

MIRNY_SETTINGS_88 = [
    MirnySettings(
        device_name="mirny_eom_707_sideband_A",
        frequency=MIRNY_SETTINGS_87[0].frequency,
        rf_switch=False,
    ),
    MirnySettings(
        device_name="mirny_eom_707_sideband_B",
        frequency=MIRNY_SETTINGS_87[1].frequency,
        rf_switch=False,
    ),
    MirnySettings(
        device_name="mirny_eom_689_sideband",
        frequency=MIRNY_SETTINGS_87[1].frequency,
        rf_switch=False,
    ),
    MirnySettings(
        device_name="mirny_eom_transfer_cavity_offset",
        frequency=1463.265e6,
        attenuation=20.0,
    ),
]


assert [s.device_name for s in MIRNY_SETTINGS_87] == [
    s.device_name for s in MIRNY_SETTINGS_88
], "Please ensure both lists are in the same order"


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
    "487": (_default_487, True),
    "689": (_default_689, False),
    "689_IJD": (
        _default_689 - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    # "689_doubled1379": (_default_689, False),
    "698": (_default_698, False),
    "Sirah": (_default_698 + _clock_laser_offset, False),
}


WAND_SETPOINTS_87 = {
    "461": (_default_461 - 60e6, True),
    "707": (_default_707 + 27e6, True),
    "679": (_default_679 - 2430e6, True),
    "487": (_default_487, True),
    "689": (_default_689 - _isotope_shift_689, False),
    "689_IJD": (
        _default_689
        - _isotope_shift_689
        - 2 * URUKULED_BEAMS["red_doublepass_injection"].frequency,
        False,
    ),
    # "689_doubled1379": (_default_689, False),
    "698": (_default_698, False),
    "Sirah": (_default_698 + _clock_laser_offset, False),
}

TOPTICA_461_ANALOG_SCALE = 210e6 / (3.05)  # MHz/V # rough value # arc factor 0.15 V/V

# Default field in chamber 1
B_FIELD_CH1_AXIAL = 0.0  # A
B_FIELD_CH1_RADIAL1 = 3.2  # A
B_FIELD_CH1_RADIAL2 = 5.4  # A


# Measure the FIELD_COMP required for zero field using Zeeman spectroscopy
# Updated 30/10/2024 based on XODT position vs MOT - possibly less reliable
# than previous calibration based on Zeeman spectroscopy
FIELD_COMP_X = 0.31
FIELD_COMP_Y = -0.009
FIELD_COMP_Z = -0.69


def add_field_offset(x, y, z):
    """
    Adds the field offset to the passed field

    Allows for easy updating of the bias field when it changes
    """
    return (
        x + FIELD_COMP_X,
        y + FIELD_COMP_Y,
        z + FIELD_COMP_Z,
    )


def calc_new_field_defaults(param_x, param_y, param_z):
    """
    Calculates the new field defaults based on the
    passed parameter value
    """
    return (
        param_x - FIELD_COMP_X,
        param_y - FIELD_COMP_Y,
        param_z - FIELD_COMP_Z,
    )


if USE_SR87:
    # With 6A gradient
    _B_FIELD_BIAS_LATTICE_X = 1.1  # A
    _B_FIELD_BIAS_LATTICE_Y = -0.02  # A
    _B_FIELD_BIAS_LATTICE_Z = -1.4  # A
else:
    # With 1A gradient
    _B_FIELD_BIAS_LATTICE_X = 0.5  # A
    _B_FIELD_BIAS_LATTICE_Y = -0.02  # A
    _B_FIELD_BIAS_LATTICE_Z = -1.01  # A

# Default fields in chamber 2 for optimising transfer into broadband red MOT
B_FIELD_BIAS_BLUE_MOT_X = FIELD_COMP_X
B_FIELD_BIAS_BLUE_MOT_Y = FIELD_COMP_Y
B_FIELD_BIAS_BLUE_MOT_Z = (
    FIELD_COMP_Y - 1.1
)  # A - optimized for 87Sr bb MOT atom number 29/11/2024

# Use the lattice bias fields if the bodgy USE_LATTICE variable is set
# TODO: Get rid of this once we're shifting lattices
if USE_LATTICE_MODE:
    B_FIELD_BIAS_BLUE_MOT_X, B_FIELD_BIAS_BLUE_MOT_Y, B_FIELD_BIAS_BLUE_MOT_Z = (
        _B_FIELD_BIAS_LATTICE_X,
        _B_FIELD_BIAS_LATTICE_Y,
        _B_FIELD_BIAS_LATTICE_Z,
    )

B_FIELD_GRADIENT = 90.0  # A


BLUE_LOADING_TIME = 500e-3
"Default blue MOT loading time"

RED_BROADBAND_RAMP_LOWER_LIMIT = -0.1e6
RED_BROADBAND_RAMP_UPPER_LIMIT = 3e6 if USE_SR87 else 4e6
"Ramp extent for the broadband red stage (n.b. will be double by the double-pass AOM)"

RED_INJECTION_AOM_RAMP_FREQUENCY = 20e3 if USE_SR87 else 30e3
"Default ramp frequency for the broadband red MOT"

RED_MOT_FINAL_HOLD_TIME = 6e-3 if USE_SR87 else 100e-3
"Default final hold time in last stage of the red mot"

# Spin polarisation settings

DELAY_BEFORE_OPTICAL_PUMPING = 20e-3
DURATION_OF_SPIN_POL = 20e-3
DELAY_AFTER_OPTICAL_PUMPING = 0e-3

# Clock stuff

CLOCK_PI_TIME = 44e-6
CLOCK_SHELVING_PULSE_TIME = 200e-6
CLOCK_SHELVING_PULSE_SETPOINT = 0.12
SHELVING_PULSE_CLEAROUT_DURATION = 2200e-6
CLOCK_DELIVERY_PREEMPT_TIME = 200e-6
DELAY_BETWEEN_INTERFEROMETRY_PULSES = 100e-6
CLOCK_DELIVERY_SPECTROSCOPY_DETUNING = 10e3

# %% Dipole trap settings

DIPOLE_TRAP_HOLD_TIME = 20e-3
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
    10e-3  # TODO: fix this by changing the ordering of the camera shutter queueing
)
if USE_SR87:
    RED_BROADBAND_SUSERVO_MULTIPLES_START = [2.2, 2.2, 2.5, 0.5]
    RED_BROADBAND_SUSERVO_MULTIPLES_END = [2.2, 2.2, 2.5, 0.5]
    RED_BROADBAND_MOT_CURRENT_START = [3.0]
    RED_BROADBAND_MOT_CURRENT_END = [10.0]
    RED_BROADBAND_DURATION = 220e-3
else:
    RED_BROADBAND_SUSERVO_MULTIPLES_START = [2.2, 2.2, 2.5, 0.0]
    RED_BROADBAND_SUSERVO_MULTIPLES_END = [2.2, 2.2, 2.5, 0.0]
    RED_BROADBAND_MOT_CURRENT_START = [9.0]
    RED_BROADBAND_MOT_CURRENT_END = [9.0]
    RED_BROADBAND_DURATION = 100e-3

# Narrowband field to load FORWARD dipole trap at 10 A MOT current Note that
# this is the default for normal red MOTs. One day we might want to split the
# red MOT and the forward XODT fields, but not today.
(
    RED_NARROWBAND_BIAS_FIELD_X,
    RED_NARROWBAND_BIAS_FIELD_Y,
    RED_NARROWBAND_BIAS_FIELD_Z,
) = add_field_offset(0.188, 0.057, -0.36)


# Narrowband field to load BACKWARD dipole trap at 10 A MOT current
(
    RED_NARROWBAND_BIAS_FIELD_BACKWARD_X,
    RED_NARROWBAND_BIAS_FIELD_BACKWARD_Y,
    RED_NARROWBAND_BIAS_FIELD_BACKWARD_Z,
) = add_field_offset(0.19, 0.029, 0.030)

RED_NARROWBAND_GRADIENT_FIELD_BACKWARD = 10


# TODO: the broadband biases are bound to blue MOT currents in RedMOTWithExperiment, so effectively ignored
# This should be confirmed and then these settings removed
RED_BROADBAND_BIAS_FIELD_START = [
    B_FIELD_BIAS_BLUE_MOT_X,
    B_FIELD_BIAS_BLUE_MOT_Y,
    B_FIELD_BIAS_BLUE_MOT_Z,
]
RED_BROADBAND_BIAS_FIELD_END = [
    RED_NARROWBAND_BIAS_FIELD_X,
    RED_NARROWBAND_BIAS_FIELD_Y,
    FIELD_COMP_Z - 0.73,
]

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
    RED_COMPRESSION_MOT_CURRENT_START = [10.0]
    RED_COMPRESSION_MOT_CURRENT_END = [10.0]
else:
    RED_COMPRESSION_DETUNING_START = [50e3]
    RED_COMPRESSION_DETUNING_END = [10e3]
    RED_COMPRESSION_SUSERVO_MULTIPLES_START = [0.1, 0.1, 0.1, 0.0]
    RED_COMPRESSION_SUSERVO_MULTIPLES_END = [0.02, 0.02, 0.02, 0.0]
    RED_COMPRESSION_MOT_CURRENT_START = [1.0]
    RED_COMPRESSION_MOT_CURRENT_END = [1.0]


### DIPOLE TRAP DEFAULT PARAMETERS ###

# Unused in Sr88 so only one setting needed
XODT_2ND_MOLASSES_689_STIR_DETUNING = 0.0e3
XODT_MOLASSES_689_STIR_DETUNING = -33000.0

# Order of suservos:
# "suservo_aom_singlepass_689_red_mot_sigmaplus",
# "suservo_aom_singlepass_689_red_mot_sigmaminus",
# "suservo_aom_singlepass_689_red_mot_diagonal",
# "suservo_aom_singlepass_689_up",
# "suservo_aom_1064_delivery",
# "suservo_aom_down_813"
# "suservo_aom_singlepass_487_transparency"
# Urukul: "urukul9910_aom_doublepass_689_red_injection"
# # Chamber 2 bias coils in amps. Order: X,Y,Z
if USE_SR87:
    RED_COMPRESSION_MOT_CURRENT_START_FOR_MOLASSES = 10.0
    RED_COMPRESSION_MOT_CURRENT_END_FOR_MOLASSES = 10.0
    RED_COMPRESSION_MOT_UP_BEAM_SETPOINT_FOR_MOLASSES = 3.5

    # This is optimized for loading into the HODT, not the XODT, because the 813
    # will be turned on during the molasses phase. The molasses phase itself
    # uses XODT_MOLASSES_BIAS_FIELD_START
    BIAS_DURING_NARROWBAND_MOT_FOR_MOLASSES = add_field_offset(0.19, 0.059, -0.39)

    DELAY_BEFORE_MOLASSES = 11e-3  # Delay between end of red MOT and start of molasses
    XODT_MOLASSES_DURATION = 400e-3
    XODT_MOLASSES_SETPOINT_MULTIPLES_START = [
        0.0007,
        0.0014,
        0.0018,
        0.008,
        1.0,
        1.0,
        0.25,
    ]
    XODT_MOLASSES_SETPOINT_MULTIPLES_END = [
        0.0007,
        0.0014,
        0.0018,
        0.008,
        1.0,
        0.7,
        0.25,
    ]
    XODT_MOLASSES_689_DETUNING_START = [
        -60e3,
    ]
    XODT_MOLASSES_689_DETUNING_END = [
        -65e3,
    ]
    XODT_MOLASSES_BIAS_FIELD_START = add_field_offset(0.0, 0.0, 0.0)
    XODT_MOLASSES_BIAS_FIELD_END = XODT_MOLASSES_BIAS_FIELD_START
    XODT_MOLASSES_MOT_CURRENT = 0.0

    DELAY_BETWEEN_MOLASSES = 0.0001e-3
    XODT_2ND_MOLASSES_DURATION = 50e-3
    XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_START = [0.0, 0.0, 0.0, 0.3, 1.0, 1.0, 1.05]
    XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_END = [0.0, 0.0, 0.0, 0.3, 1.0, 1.0, 1.05]
    XODT_2ND_MOLASSES_689_DETUNING_START = [
        -35e3,
    ]
    XODT_2ND_MOLASSES_689_DETUNING_END = [
        -48e3,
    ]
    XODT_2ND_MOLASSES_BIAS_FIELD_START = add_field_offset(0.0, 0.0, 0.0)
    XODT_2ND_MOLASSES_BIAS_FIELD_END = XODT_MOLASSES_BIAS_FIELD_START
    XODT_2ND_MOLASSES_MOT_CURRENT = 0.0
else:
    DELAY_BEFORE_MOLASSES = 0.01e-3
    RED_COMPRESSION_MOT_CURRENT_START_FOR_MOLASSES = 6.0
    RED_COMPRESSION_MOT_CURRENT_END_FOR_MOLASSES = 6.0
    RED_COMPRESSION_MOT_UP_BEAM_SETPOINT_FOR_MOLASSES = 0.0

    XODT_MOLASSES_DURATION = 120e-3
    XODT_MOLASSES_SETPOINT_MULTIPLES_START = [0.02, 0.02, 0.02, 0.0, 1.0, 1.0, 1.05]
    XODT_MOLASSES_SETPOINT_MULTIPLES_END = [0.02, 0.02, 0.02, 0.0, 1.0, 1.0, 1.05]
    XODT_MOLASSES_689_DETUNING_START = [
        100e3,
    ]
    XODT_MOLASSES_689_DETUNING_END = [
        120e3,
    ]
    XODT_MOLASSES_BIAS_FIELD_START = add_field_offset(0.148, 0.024, -0.58)
    XODT_MOLASSES_BIAS_FIELD_END = XODT_MOLASSES_BIAS_FIELD_START
    BIAS_DURING_NARROWBAND_MOT_FOR_MOLASSES = XODT_MOLASSES_BIAS_FIELD_START
    XODT_MOLASSES_MOT_CURRENT = 6.0

    DELAY_BETWEEN_MOLASSES = 0.01e-3
    XODT_2ND_MOLASSES_DURATION = 0.01e-3
    XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_START = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
    XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_END = [0.05, 0.05, 0.05, 0.2, 1.0, 1.0]
    XODT_2ND_MOLASSES_689_DETUNING_START = [
        0e3,
    ]
    XODT_2ND_MOLASSES_689_DETUNING_END = [
        0e3,
    ]
    XODT_2ND_MOLASSES_BIAS_FIELD_START = add_field_offset(0.0, 0.0, 0.0)
    XODT_2ND_MOLASSES_BIAS_FIELD_END = add_field_offset(0.0, 0.0, 0.0)
    XODT_2ND_MOLASSES_MOT_CURRENT = 0.0

OPTICAL_PUMPING_BIAS_FIELD = add_field_offset(0.0, 0.5, 0.0)

XODT_COOL_MOLASSES_MULTIPLE_START = [1, 0.7]
XODT_COOL_MOLASSES_MULTIPLE_END = [1.0, 0.7]

XODT_EVAP_AND_FIELD_RAMP_DURATION = 200e-3
XODT_EVAP_DURATION = 1400e-3
XODT_EVAP_2_DURATION = 1000e-3
XODT_EVAP_3_DURATION = 1300e-3
# SUServo order: [1064 delivery, down 813]
XODT_EVAP_START = [1.0, 0.7]
XODT_EVAP_END = [0.35, 0.7]
XODT_EVAP_AND_FIELD_RAMP_SUSERVOS_END = [1.0, 1.0]
XODT_EVAP_AND_FIELD_RAMP_FIELD_START = OPTICAL_PUMPING_BIAS_FIELD
XODT_EVAP_AND_FIELD_RAMP_FIELD_END = add_field_offset(-1.12, 0.0, 0.0)
# XODT_EVAP_AND_FIELD_RAMP_FIELD_END = [
#     a + b for a, b in zip(FIELD_COMP, [0.0, 0.0, 2.0])
# ]

XODT_EVAP_2_END = [0.21, 0.7]

XODT_EVAP_3_END = [0.18, 0.7]

CLOCK_LASER_BEATNOTE_FREQUENCY = 80e6  # this is set on the rigol for the clock laser lock. if you change that, change this.

# Single dipole trap loading phase
# order diagonal, sigmaplus, sigmaminus, up, 1064, 813
XODT_SINGLE_LOADING_DURATION = 100e-3


XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_START = [0.025, 0.02, 0.03, 0.16, 0.5, 0.5]
XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_END = [0.001, 0.005, 0.005, 0.003, 1.0, 1.0]
XODT_SINGLE_LOADING_689_DETUNING_START = [
    0e3,
]
XODT_SINGLE_LOADING_689_DETUNING_END = [
    -5e3,
]
RED_COMPRESSION_MOT_UP_BEAM_SETPOINT_FOR_SINGLE_XODT = 3.5
XODT_SINGLE_LOADING_STIR_DETUNING = +13e3
XODT_SINGLE_NARROWBAND_COMPRESSION_GRADIENT = 10.0

TOTAL_EVAP_HOLD_TIME = 5.0

# %% Second dipole trap loading phase
# order diagonal, sigmaplus, sigmaminus, up

XXODT_LOWER_LOADING_DURATION = (
    100e-3  # Good when using the transparancy beam to protect the top trap
)
XXODT_LOWER_LOADING_WAIT_BEFORE = 3e-3
XXODT_LOWER_LOADING_SETPOINT_MULTIPLES_START = (
    XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_START[:4]
)
XXODT_LOWER_LOADING_SETPOINT_MULTIPLES_END = (
    XXODT_LOWER_LOADING_SETPOINT_MULTIPLES_START
)
XXODT_LOWER_LOADING_689_STIR_DETUNING = XODT_SINGLE_LOADING_STIR_DETUNING


# %% Dedrifter settings


_CAVITY_RAMP_RATE = (
    0.052  # Hz/s based on ~9 kHz drift over 24 hours, through a frequency doubler
)


_CAVITY_OFFSET_689 = 331.543688e6
_REFERENCE_TIME_689 = 1739450287
_CAVITY_RAMP_RATE_689 = _CAVITY_RAMP_RATE

# to put at the right place, move by half the detuning on the AOM (AOM double passed)
# in thesame direction as we want to steer the detuning (AOM positively passed)
_CAVITY_OFFSET_698 = 335.95e6
# 336.137e6  # 336.437e6  #  337.4035e6  # 673.54e6 / 2  # 336.77e6
_REFERENCE_TIME_698 = 1750511992
_CAVITY_RAMP_RATE_698 = -_CAVITY_RAMP_RATE


if not USE_SR87:  # TODO be smarter
    # Account for isotope shifts, remembering that the output frequency is
    # doubled and that the Sr-88 lock uses a negative sideband
    _CAVITY_RAMP_RATE_689 *= -1
    _CAVITY_OFFSET_689 = _isotope_shift_689 / 2 - _CAVITY_OFFSET_689


# Time step for dedrifting steps
T_STEP_DEDRIFTER = 100e-6


@dataclass
class DedrifterInfo:
    laser_name: str
    channel_name: str
    reference_frequency: float
    reference_time: int
    ramp_rate: float
    attenuation = 0.0


_DEDRIFTER_INFO_689 = DedrifterInfo(
    "689",
    "urukul0_ch0",
    _CAVITY_OFFSET_689,
    _REFERENCE_TIME_689,
    _CAVITY_RAMP_RATE_689,
)
_DEDRIFTER_INFO_698 = DedrifterInfo(
    "698",
    "urukul0_ch1",
    _CAVITY_OFFSET_698,
    _REFERENCE_TIME_698,
    _CAVITY_RAMP_RATE_698,
)

DEDRIFTER_INFOS = [_DEDRIFTER_INFO_689, _DEDRIFTER_INFO_698]

## Clock glitch filter

CLOCK_GLITCH_FILTER_GLITCH_THRESHOLD = 0.03  # volts
CLOCK_GLITCH_FILTER_GATE_THRESHOLD = 2.0  # volts
CLOCK_GLITCH_FILTER_GATE_DURATION = 500e-6  # seconds
