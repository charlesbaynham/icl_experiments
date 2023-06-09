import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM

import repository.lib.constants as constants
from repository.lib.fragments.ad9910_ramper import AD9910Ramper
from repository.lib.fragments.beam_setters import SetBeamsToDefaults


logger = logging.getLogger(__name__)


class Red3DMOTFrag(Fragment):
    """
    Methods for making and controlling the red 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter",
            SetBeamsToDefaults,
            beams_to_enable=[
                "red_MOT_diag",
                "red_MOT_axialplus",
                "red_MOT_axialminus",
            ],
        )
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "all_mot_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["red_MOT_diag"],
                constants.AOM_BEAMS["red_MOT_axialplus"],
                constants.AOM_BEAMS["red_MOT_axialminus"],
            ],
        )
        self.all_mot_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "injection_aom_dds",
            AD9910Ramper,
            "urukul9910_aom_doublepass_689_red_injection",
        )
        self.injection_aom_dds: AD9910Ramper

        self.injection_aom: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )

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

        # Start the injection AOM in static mode
        self.injection_aom.cpld.get_att_mu()  # retrive current attenuation settings
        self.injection_aom.set(constants.RED_INJECTION_AOM_FREQUENCY)
        self.injection_aom.set_att(constants.RED_INJECTION_AOM_ATTENUATION)

    @kernel
    def turn_on_mot_beams(self):
        self.all_mot_beams_setter.turn_beams_on()

    @kernel
    def turn_off_mot_beams(self):
        self.all_mot_beams_setter.turn_beams_off()
