import logging

from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.magnetic_fields import SetMagneticFields

logger = logging.getLogger(__name__)


class BlueBeamSetter(SetBeamsToDefaults):
    beam_infos = [
        constants.AOM_BEAMS[beam]
        for beam in [
            # FIXME: commented out most blue beams
            # "blue_push_beam",
            # "blue_2dmot_A",
            "blue_2dmot_B",
            # "blue_3dmot_radial",
            # "blue_3dmot_axialplus",
            # "blue_3dmot_axialminus",
            # "blue_injection",
            # "repump_707",
            # "repump_679",
        ]
    ]


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT

    Note that the user must call init() before this object is used
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("all_beam_default_setter", BlueBeamSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "mot_all_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["blue_push_beam"],
                constants.AOM_BEAMS["blue_3dmot_radial"],
                constants.AOM_BEAMS["blue_3dmot_axialplus"],
                constants.AOM_BEAMS["blue_3dmot_axialminus"],
                constants.AOM_BEAMS["blue_2dmot_A"],
                constants.AOM_BEAMS["blue_2dmot_B"],
                constants.AOM_BEAMS["repump_679"],
                constants.AOM_BEAMS["repump_707"],
            ],
        )
        self.mot_all_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_2d_and_3d_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["blue_push_beam"],
                constants.AOM_BEAMS["blue_3dmot_radial"],
                constants.AOM_BEAMS["blue_3dmot_axialplus"],
                constants.AOM_BEAMS["blue_3dmot_axialminus"],
                constants.AOM_BEAMS["blue_2dmot_A"],
                constants.AOM_BEAMS["blue_2dmot_B"],
            ],
        )
        self.mot_2d_and_3d_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_3d_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["blue_3dmot_radial"],
                constants.AOM_BEAMS["blue_3dmot_axialplus"],
                constants.AOM_BEAMS["blue_3dmot_axialminus"],
            ],
        )
        self.mot_3d_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "repump_beam_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["repump_679"],
                constants.AOM_BEAMS["repump_707"],
            ],
        )
        self.repump_beam_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFields,
        )
        self.chamber_2_field_setter: SetMagneticFields

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
            default=300e-3,
            unit="ms",
            min=0,
        )
        self.loading_time: FloatParamHandle

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

    @kernel
    def init(self):
        """
        Set up beam state for the blue MOT, i.e. set up AOMs and close all shutters

        This is not in device_setup so that the user can choose when / whether to call it during each scan cycle
        """

        # Turn on all the AOMs but close all the shutters
        delay(200e-6)  # We need some slack - create it deterministically
        self.all_beam_default_setter.turn_on_all(shutter_state=False)

    @kernel
    def enable_mot_fields(self):
        """
        Turn on the MOT gradient and bias fields

        This method advances the timeline by a ridiculous amount and does not
        respect beam shutter delays - it just turns everything
        on immediately. It needs at least 3924ns of slack.

        FIXME: Figure out why I need a stupid amount of slack
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
    def enable_mot_defaults(self):
        """
        Immediately turn on all beams and fields related to the 3D blue MOT
        """
        self.all_beam_default_setter.turn_on_all()
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
    def turn_on_3d_beams(self):
        return self.mot_3d_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_beams(self):
        return self.mot_3d_beams_setter.turn_beams_off()

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

        # FIXME: debug comments

        # self.enable_mot_fields()

        # if clearout:
        #     self.clear_ch2()

        self.turn_on_all_beams()
        delay(self.loading_time.get())
