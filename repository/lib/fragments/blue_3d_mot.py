import logging
from typing import List

from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.toggle_beams_with_AOM_and_shutter import (
    ControlBeamsWithoutCoolingAOM,
)
from pyaion.models import UrukuledBeam

import repository.lib.constants as constants
from repository.lib.fragments.beams.reset_all_beams import ResetAllICLBeams
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsSlow
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndMOTField,
)
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsExceptCavity

logger = logging.getLogger(__name__)

# The blue 2D MOT beams are now delivered freespace, direct to the atoms. There
# is therefore no AOM and no SUServo, but there are shutters so we handle them
# directly:
BLUE_2D_MOT_SHUTTERS = [
    "TTL_shutter_461_2dmot_is_it_a",
    "TTL_shutter_461_2dmot_is_it_b",
]


BlueBeamSetter = make_set_beams_to_default(
    suservo_beam_infos=[
        constants.SUSERVOED_BEAMS[beam]
        for beam in [
            "blue_push_beam",
            "blue_3dmot_radial",
            "blue_3dmot_axialplus",
            "blue_3dmot_axialminus",
            "repump_707",
            "repump_679",
        ]
    ],
    urukul_beam_infos=[],
    name="BlueBeamSetter",
)

BLUE_DOUBLEPASS_INJECTION_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS[
    "blue_doublepass_injection"
]
BLUE_SINGLEPASS_INJECTION_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS[
    "blue_singlepass_injection"
]
BLUE_DOUBLEPASS_XFER_CAVITY_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS[
    "blue_xfer_offset"
]


class BlueRampingPhaseWithFields(GeneralRampingPhaseWithBindingAndMOTField):
    """
    Subclass the GeneralRampingPhase specifically for the blue MOT transfer phase. I.e.:

    * Control the 3 blue 3D MOT beams
    * Add control of the B fields in chamber 2
    """

    duration_default = constants.BLUE_TRANSFER_MOT_DURATION
    time_step_default = constants.BLUE_TRANSFER_MOT_RAMP_TIMESTEP

    suservos = [
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "suservo_aom_singlepass_461_3DMOT_radial",
    ]
    default_suservo_nominal_setpoints = [
        0.0
    ] * 3  # The nominal setpoints will be retrieved from default beam setter settings (usually set in constants SUServo list, but also an exposed parameter)
    default_suservo_setpoint_multiples_start = (
        constants.BLUE_TRANSFER_MOT_SUSERVO_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.BLUE_TRANSFER_MOT_SUSERVO_MULTIPLES_END
    )
    general_setter_default_starts = [constants.BLUE_TRANSFER_MOT_GRADIENT_START]
    general_setter_default_ends = [constants.BLUE_TRANSFER_MOT_GRADIENT_END]


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT

    If manual_init=True is passed to build_fragment, the user must call init()
    before this object is used
    """

    def build_fragment(self, manual_init=False):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "mirny_eom_sidebands", SetEOMSidebandsExceptCavity, init_mirnys=False
        )
        self.mirny_eom_sidebands: SetEOMSidebandsExceptCavity

        self.setattr_param_rebind("sr87", self.mirny_eom_sidebands)
        self.sr87: BoolParamHandle

        self.setattr_fragment("reset_all_beams", ResetAllICLBeams)

        self.doublepass_injection_aom: AD9912 = self.get_device(
            BLUE_DOUBLEPASS_INJECTION_BEAM_INFO.urukul_device
        )

        self.singlepass_injection_aom: AD9912 = self.get_device(
            BLUE_SINGLEPASS_INJECTION_BEAM_INFO.urukul_device
        )

        self.doublepass_xfer_cavity_aom: AD9912 = self.get_device(
            BLUE_DOUBLEPASS_XFER_CAVITY_BEAM_INFO.urukul_device
        )

        self.setattr_fragment("all_beam_default_setter", BlueBeamSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.blue_2d_mot_shutters: List[TTLOut] = [
            self.get_device(d) for d in BLUE_2D_MOT_SHUTTERS
        ]
        self.kernel_invariants.add("blue_2d_mot_shutters")

        self.setattr_fragment(
            "mot_all_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
                constants.SUSERVOED_BEAMS["repump_679"],
                constants.SUSERVOED_BEAMS["repump_707"],
                constants.SUSERVOED_BEAMS["blue_push_beam"],
            ],
        )
        self.mot_all_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "blue_push_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_push_beam"],
            ],
        )
        self.blue_push_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_2d_and_3d_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
                constants.SUSERVOED_BEAMS["blue_push_beam"],
            ],
        )
        self.mot_2d_and_3d_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_2d_and_3d_beams_nopush_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
            ],
        )
        self.mot_2d_and_3d_beams_nopush_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_3d_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
            ],
        )
        self.mot_3d_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_all_beams_except_radial_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
                constants.SUSERVOED_BEAMS["repump_679"],
                constants.SUSERVOED_BEAMS["repump_707"],
                constants.SUSERVOED_BEAMS["blue_push_beam"],
            ],
        )
        self.mot_all_beams_except_radial_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "radial_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
            ],
        )
        self.radial_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "repump_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["repump_679"],
                constants.SUSERVOED_BEAMS["repump_707"],
            ],
        )
        self.repump_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        self.setattr_fragment(
            "chamber_1_field_setter",
            SetMagneticFieldsSlow,
        )
        self.chamber_1_field_setter: SetMagneticFieldsSlow

        self.setattr_fragment(
            "blue_transfer_MOT",
            BlueRampingPhaseWithFields,
        )
        self.blue_transfer_MOT: BlueRampingPhaseWithFields

        # Bind the SUServo setpoint parameters to those defined in the red default beam setter
        self.blue_transfer_MOT.bind_suservo_setpoint_params_to_default_beam_setter(
            self.all_beam_default_setter
        )

        self.setattr_param(
            "delay_into_red_mot_for_blue_beam_switchoff",
            FloatParam,
            "Delay into red mot before blue beams switch off",
            default=constants.DELAY_INTO_RED_MOT_FOR_BLUE_BEAM_SWITCHOFF,
            unit="us",
        )
        self.delay_into_red_mot_for_blue_beam_switchoff: FloatParamHandle

        self.setattr_param(
            "chamber_2_bias_x",
            FloatParam,
            "Bias current for chamber 2 - X",
            default=constants.B_FIELD_BIAS_BLUE_MOT_X,
            unit="A",
            min=-5,
            max=5,
        )
        self.setattr_param(
            "chamber_2_bias_y",
            FloatParam,
            "Bias current for chamber 2 - Y",
            default=constants.B_FIELD_BIAS_BLUE_MOT_Y,
            unit="A",
            min=-5,
            max=5,
        )
        self.setattr_param(
            "chamber_2_bias_z",
            FloatParam,
            "Bias current for chamber 2 - Z",
            default=constants.B_FIELD_BIAS_BLUE_MOT_Z,
            unit="A",
            min=-5,
            max=5,
        )
        self.chamber_2_bias_x: FloatParamHandle
        self.chamber_2_bias_y: FloatParamHandle
        self.chamber_2_bias_z: FloatParamHandle

        self.setattr_param(
            "chamber_2_field_gradient",
            FloatParam,
            "Field gradient current for chamber 2",
            default=constants.B_FIELD_GRADIENT,
            unit="A",
            min=0,
            max=130,
        )
        self.chamber_2_field_gradient: FloatParamHandle

        self.setattr_param(
            "clearout_time",
            FloatParam,
            "Time to clear out atoms for",
            default=100e-3,
            unit="ms",
            min=0,
        )
        self.clearout_time: FloatParamHandle

        self.setattr_param(
            "blue_doublepass_injection_detuning",
            FloatParam,
            "Detuning of blue doublepass injection AOM from nominal",
            default=0,
            unit="MHz",
            min=0,
        )
        self.blue_doublepass_injection_detuning: FloatParamHandle

        self.setattr_param(
            "loading_time",
            FloatParam,
            "Time to load atoms for",
            default=constants.BLUE_LOADING_TIME,
            unit="ms",
            min=0,
        )
        self.loading_time: FloatParamHandle

        self.setattr_param(
            "blue_xfer_cavity_detuning_jump",
            FloatParam,
            "Detuning jump of blue xfer cavity AOM from nominal",
            default=0,
            unit="MHz",
            min=0,
        )
        self.blue_xfer_cavity_detuning_jump: FloatParamHandle

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)
        self.manual_init = manual_init

        # %% Kernel invariants
        self.kernel_invariants.add("debug_mode")
        self.kernel_invariants.add("manual_init")

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        if not self.manual_init:
            self.core.break_realtime()
            self.init()

    @kernel
    def init(self):
        """
        Set up beam state for the blue MOT

        This configured all SUServos to the right frequency, setpoint and
        attenuation. If a shutter exists, the shutter is closed and the AOM is
        turned on. If there is no shutter, the SUServo's RF switch is set to
        off.

        This is called automatically by device_setup unless `manula_init=True`
        was passed to build_fragment.
        """

        # Turn on all the AOMs but close all the shutters
        delay(400e-6)  # We need some slack - create it deterministically
        self.all_beam_default_setter.turn_on_all(light_enabled=False)

        self.doublepass_injection_aom.set(
            frequency=BLUE_DOUBLEPASS_INJECTION_BEAM_INFO.frequency
            + self.blue_doublepass_injection_detuning.get()
        )
        self.singlepass_injection_aom.set(
            frequency=BLUE_SINGLEPASS_INJECTION_BEAM_INFO.frequency
        )

        self.mirny_eom_sidebands.set_sidebands()

    @kernel
    def enable_mot_fields(self):
        """
        Turn on the MOT gradient and bias fields

        This method advances the timeline by a ridiculous amount and does not
        respect beam shutter delays - it just turns everything
        on immediately. It needs at least 3924ns of slack.

        TODO: Figure out why I need a stupid amount of slack
        """

        if self.debug_mode:
            logger.info("Enabling MOT fields")

        delay(50e-3)
        self.chamber_2_field_setter.set_bias_fields(
            self.chamber_2_bias_x.get(),
            self.chamber_2_bias_y.get(),
            self.chamber_2_bias_z.get(),
        )
        delay(50e-3)
        self.chamber_2_field_setter.set_mot_gradient(
            self.chamber_2_field_gradient.get()
        )

    @kernel
    def enable_mot_defaults(self, light_enabled=True):
        """
        Immediately turn on all beams and fields related to the 3D blue MOT
        """
        self.all_beam_default_setter.turn_on_all(light_enabled=light_enabled)
        self.enable_mot_fields()

    @kernel
    def _set_2d_mot_shutters(self, state: bool):
        """
        Set the state of the 2D MOT shutters

        :param state: True to open, False to close
        """
        for shutter in self.blue_2d_mot_shutters:
            shutter.set_o(state)
            # Avoid multiple lane usage:
            delay_mu(self.core.seconds_to_mu(self.core.coarse_ref_period))

    @kernel
    def turn_on_3d_and_2d_beams(self):
        self.mot_2d_and_3d_beams_setter.turn_beams_on()
        self._set_2d_mot_shutters(True)

    @kernel
    def turn_off_3d_and_2d_beams(self):
        self._set_2d_mot_shutters(False)
        self.mot_2d_and_3d_beams_setter.turn_beams_off()

    @kernel
    def turn_on_all_beams(self):
        self.mot_all_beam_setter.turn_beams_on()
        self._set_2d_mot_shutters(True)

    @kernel
    def turn_off_all_beams(self):
        self.mot_all_beam_setter.turn_beams_off()
        self._set_2d_mot_shutters(False)

    @kernel
    def turn_on_push_beam(self):
        self.blue_push_beam_setter.turn_beams_on()

    @kernel
    def turn_off_push_beam(self):
        self.blue_push_beam_setter.turn_beams_off()

    @kernel
    def turn_on_3d_beams(self, ignore_shutters=False):
        self.mot_3d_beams_setter.turn_beams_on(ignore_shutters=ignore_shutters)

    @kernel
    def turn_off_3d_beams(self, ignore_shutters=False):
        """Turn off the 3D blue MOT beams

        This method will not advance the cursor BUT will write shutter closing
        events into the future by "shutter_delay_time" seconds.
        """
        self.mot_3d_beams_setter.turn_beams_off(ignore_shutters=ignore_shutters)

    @kernel
    def turn_on_repumpers(self):
        self.repump_beam_setter.turn_beams_on()

    @kernel
    def turn_off_repumpers(self):
        self.repump_beam_setter.turn_beams_off()

    @kernel
    def turn_off_all_beams_except_radial(self, ignore_shutters=False):
        return self.mot_all_beams_except_radial_setter.turn_beams_off(
            ignore_shutters=ignore_shutters
        )

    @kernel
    def turn_off_radial_beams(self, ignore_shutters=False):
        return self.radial_beam_setter.turn_beams_off(ignore_shutters=ignore_shutters)

    @kernel
    def clear_ch2(self):
        """
        Clear out atoms from chamber 2
        """

        # Turn on the repumps and turn off everything else
        self.turn_on_repumpers()
        delay(1e-6)
        self.turn_off_3d_and_2d_beams()

        # Wait to allow atoms to disperse if there were any hanging around
        delay(self.clearout_time.get())

    @kernel
    def load_mot(self, clearout=True):
        """
        Load a blue 3D MOT using the configured parameters

        Optionally clear out atoms first
        """

        if self.debug_mode:
            slack_mu = now_mu() - self.core.get_rtio_counter_mu()
            logger.info("Loading a blue MOT with clearout = %s", clearout)
            at_mu(self.core.get_rtio_counter_mu() + slack_mu)

        self.enable_mot_fields()

        if clearout:
            self.clear_ch2()

        self.turn_on_all_beams()
        delay(self.loading_time.get())

    @kernel
    def load_magnetic_trap(self, repump_at_end=True):
        """
        Load the magnetic trap, then optionally repump at the end
        """

        self.enable_mot_fields()
        self.turn_on_3d_and_2d_beams()
        self.turn_off_repumpers()
        delay(self.loading_time.get())
        if repump_at_end:
            self.turn_on_repumpers()

    @kernel
    def do_blue_transfer_mot(self):
        """
        Perform the blue transfer mot phase

        Advances the timeline by the duration of the blue transfer MOT
        """
        self.turn_off_push_beam()
        delay_mu(int64(self.core.ref_multiplier))
        self.doublepass_xfer_cavity_aom.set(
            frequency=BLUE_DOUBLEPASS_XFER_CAVITY_BEAM_INFO.frequency
            + self.blue_xfer_cavity_detuning_jump.get()
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.blue_transfer_MOT.do_phase()
        delay_mu(int64(self.core.ref_multiplier))
        self.doublepass_xfer_cavity_aom.set(
            frequency=BLUE_DOUBLEPASS_XFER_CAVITY_BEAM_INFO.frequency
        )
