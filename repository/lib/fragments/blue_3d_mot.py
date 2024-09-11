import logging

from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import TFloat
from artiq.experiment import TList
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.toggle_beams_with_AOM_and_shutter import (
    ControlBeamsWithoutCoolingAOM,
)

import repository.lib.constants as constants
from repository.lib.fragments.beams.reset_all_beams import ResetAllICLBeams
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsSlow
from repository.lib.fragments.ramping_phase import GeneralRampingPhase

logger = logging.getLogger(__name__)


BlueBeamSetter = make_set_beams_to_default(
    suservo_beam_infos=[
        constants.SUSERVOED_BEAMS[beam]
        for beam in [
            "blue_push_beam",
            "blue_2dmot_A",
            "blue_2dmot_B",
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


class BlueRampingPhaseWithFields(GeneralRampingPhase):
    """
    Subclass the GeneralRampingPhase specifically for the blue MOT transfer phase. I.e.:

    * Control the 3 blue 3D MOT beams
    * Add control of the B fields in chamber 2
    """

    duration_default = constants.BLUE_TRANSFER_MOT_DURATION
    time_step_default = 1e-3

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

    # The general ramp here ramps the chamber 2 MOT coils in amps
    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(self, chamber_2_field_setter: SetMagneticFieldsQuick = None):
        if chamber_2_field_setter is None:
            raise TypeError("You must pass chamber_2_field_setter into build_fragment")
        self.field_setter = chamber_2_field_setter
        self.__binding_completed = False
        return super().build_fragment()

    def host_setup(self):
        if not self.__binding_completed:
            raise TypeError(
                "bind_suservo_setpoint_params_to_default_beam_setter has not been called\n"
                "This must be called from the Fragment which initiates this phase to rebind the blue beam setpoints"
            )
        return super().host_setup()

    @kernel
    def general_setter(self, vals: TList(TFloat)):
        self.field_setter.set_mot_gradient(vals[0])

    @host_only
    def bind_suservo_setpoint_params_to_default_beam_setter(
        self, beam_setter: SetBeamsToDefaults
    ):
        """
        Use the GeneralRampingPhase's :meth:`~.bind_suservo_setpoint_params`
        method to bind all this GeneralRampingPhase's suservo setpoint
        parameters to those defined by a `SetBeamsToDefaults`.

        This is a slightly ugly thing to do since it couples two objects that
        shouldn't need to know about each other, i.e. the GeneralRampingPhase
        whose responsibility is to ramp SUServo setpoints (and other things)
        and the SetBeamsToDefaults object whose responsibility it is to set up
        SUServos with their default settings.

        However, by doing it like this there is a single place in the ndscan
        parameter tree where all the setpoints for the blue beams are defined,
        i.e. in the SetBeamsToDefaults owned by the Blue3DMOTFrag. This
        method glues those two objects together, but I'm adding it here in the
        blue MOT module since Charles previously chose to keep the GeneralRampingPhase code
        decoupled from the beam_setter module.
        """
        # For the SUServo setpoints, bind these to the FloatParameters defined
        # by the DefaultBeamSetter so that this is the only place which defines
        # SUServo setpoints
        info_and_settings = list(beam_setter.get_setpoints_beaminfo_setters().values())
        handles = []
        for suservo_device_name in self.suservos:
            for info, settings in info_and_settings:
                if info.suservo_device == suservo_device_name:
                    handles.append(settings.setpoint_handle)
                    break
            else:
                raise ValueError(
                    f"SUServo {suservo_device_name} not found in all_beam_default_setter"
                )
        self.bind_suservo_setpoint_params(handles)
        self.__binding_completed = True


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT

    If manual_init=True is passed to build_fragment, the user must call init()
    before this object is used
    """

    def build_fragment(self, manual_init=False):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("reset_all_beams", ResetAllICLBeams)

        self.setattr_fragment("all_beam_default_setter", BlueBeamSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "mot_all_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.SUSERVOED_BEAMS["blue_push_beam"],
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
                constants.SUSERVOED_BEAMS["blue_2dmot_A"],
                constants.SUSERVOED_BEAMS["blue_2dmot_B"],
                constants.SUSERVOED_BEAMS["repump_679"],
                constants.SUSERVOED_BEAMS["repump_707"],
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
                constants.SUSERVOED_BEAMS["blue_push_beam"],
                constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialplus"],
                constants.SUSERVOED_BEAMS["blue_3dmot_axialminus"],
                constants.SUSERVOED_BEAMS["blue_2dmot_A"],
                constants.SUSERVOED_BEAMS["blue_2dmot_B"],
            ],
        )
        self.mot_2d_and_3d_beams_setter: ControlBeamsWithoutCoolingAOM

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
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.blue_transfer_MOT: BlueRampingPhaseWithFields

        # Bind the SUServo setpoint parameters to those defined in the red default beam setter
        self.blue_transfer_MOT.bind_suservo_setpoint_params_to_default_beam_setter(
            self.all_beam_default_setter
        )

        self.setattr_param(
            "chamber_2_bias_x",
            FloatParam,
            "Bias current for chamber 2 - X",
            default=constants.B_FIELD_BIAS_X,
            unit="A",
            min=-5,
            max=5,
        )
        self.setattr_param(
            "chamber_2_bias_y",
            FloatParam,
            "Bias current for chamber 2 - Y",
            default=constants.B_FIELD_BIAS_Y,
            unit="A",
            min=-5,
            max=5,
        )
        self.setattr_param(
            "chamber_2_bias_z",
            FloatParam,
            "Bias current for chamber 2 - Z",
            default=constants.B_FIELD_BIAS_Z,
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
            "loading_time",
            FloatParam,
            "Time to load atoms for",
            default=constants.BLUE_LOADING_TIME,
            unit="ms",
            min=0,
        )
        self.loading_time: FloatParamHandle

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)
        self.manual_init = manual_init

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "manual_init"}

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
        delay(200e-6)  # We need some slack - create it deterministically
        self.all_beam_default_setter.turn_on_all(light_enabled=False)

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
    def turn_on_3d_and_2d_beams(self):
        return self.mot_2d_and_3d_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_and_2d_beams(self):
        return self.mot_2d_and_3d_beams_setter.turn_beams_off()

    @kernel
    def turn_on_all_beams(self):
        return self.mot_all_beam_setter.turn_beams_on()

    @kernel
    def turn_off_all_beams(self):
        return self.mot_all_beam_setter.turn_beams_off()

    @kernel
    def turn_on_push_beam(self):
        return self.blue_push_beam_setter.turn_beams_on()

    @kernel
    def turn_off_push_beam(self):
        return self.blue_push_beam_setter.turn_beams_off()

    @kernel
    def turn_on_3d_beams(self, ignore_shutters=False):
        return self.mot_3d_beams_setter.turn_beams_on(ignore_shutters=ignore_shutters)

    @kernel
    def turn_off_3d_beams(self, ignore_shutters=False):
        """Turn off the 3D blue MOT beams

        This method will not advance the cursor BUT will write shutter closing
        events into the future by "shutter_delay_time" seconds.
        """
        return self.mot_3d_beams_setter.turn_beams_off(ignore_shutters=ignore_shutters)

    @kernel
    def turn_on_repumpers(self):
        return self.repump_beam_setter.turn_beams_on()

    @kernel
    def turn_off_repumpers(self):
        return self.repump_beam_setter.turn_beams_off()

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
    def do_blue_transfer_mot(self):
        """
        Perform the blue transfer mot phase

        Advances the timeline by the duration of the blue transfer MOT
        """
        self.turn_off_push_beam()
        self.blue_transfer_MOT.do_phase()
