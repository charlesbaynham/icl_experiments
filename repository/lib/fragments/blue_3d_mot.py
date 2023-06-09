import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.magnetic_fields import SetMagneticFields

logger = logging.getLogger(__name__)


BLUE_3D_MOT_BEAMS = [
    "blue_push_beam",
    "blue_2dmot_A",
    "blue_2dmot_B",
    "blue_3dmot_radial",
    "blue_3dmot_axialplus",
    "blue_3dmot_axialminus",
    "blue_injection",
    "repump_707",
    "repump_679",
]


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter",
            SetBeamsToDefaults,
            beams_to_enable=BLUE_3D_MOT_BEAMS,
        )
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "all_mot_beams_setter",
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
        self.all_mot_beams_setter: ControlBeamsWithoutCoolingAOM

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
            max=100,
        )
        self.chamber_2_field_gradient: FloatParamHandle

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Turn on all the AOMs but close all the shutters
        self.core.break_realtime()
        self.all_beam_default_setter.turn_on_all(shutter_state=False)

        # Make sure that the shutters are closed before run_once starts
        delay(self.all_beam_default_setter.get_max_shutter_delay())

    @kernel
    def enable_mot_defaults(self):
        """
        Immediately turn on all beams and fields related to the 3D blue MOT

        This method advances the timeline by a ridiculous amount and does not
        respect beam shutter delays - it just turns everything
        on immediately. It needs at least 3924ns of slack.

        FIXME: Figure out why I need a stupid amount of slack
        """
        self.all_beam_default_setter.turn_on_all()
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
    def turn_on_3d_and_2d_beams(self):
        self.all_mot_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_and_2d_beams(self):
        self.all_mot_beams_setter.turn_beams_off()

    @kernel
    def turn_on_3d_beams(self):
        self.mot_3d_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_beams(self):
        self.mot_3d_beams_setter.turn_beams_off()
