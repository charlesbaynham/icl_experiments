import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle


import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults, ControlBeamWithoutCoolingAOM

logger = logging.getLogger(__name__)


BLUE_3D_MOT_BEAMS = [
    "blue_push_beam",
    "blue_2dmot_A",
    "blue_2dmot_B",
    "blue_3dmot_radial",
    "blue_3dmot_axialplus",
    "blue_3dmot_axialminus",
    "blue_injection",
]


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("all_beam_default_setter", SetBeamsToDefaults, beams_to_enable=BLUE_3D_MOT_BEAMS)
        self.all_beam_default_setter: SetBeamsToDefaults

        # Give us access to on/off methods for the push beam and the 3D MOT beams
        for beam_name in [
            "blue_push_beam",
            "blue_3dmot_radial",
            "blue_3dmot_axialplus",
            "blue_3dmot_axialminus",
        ]:
            beam_info = constants.AOM_BEAMS[beam_name]
            self.setattr_fragment(f"{beam_name}_setter",
                                  ControlBeamWithoutCoolingAOM, beam_info=beam_info)
        
        self.blue_push_beam_setter : ControlBeamWithoutCoolingAOM
        self.blue_3dmot_radial_setter : ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialplus_setter : ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialminus_setter : ControlBeamWithoutCoolingAOM



    @kernel
    def enable_mot_beams(self):
        """
        Immediately turn on all beams related to the 3D blue MOT

        This method does not advance the timeline and does not
        respect beam shutter delays - it just turns everything
        on immediately. 
        """
        self.all_beam_default_setter.turn_on_all()

    @kernel
    def turn_on_push_beam(self):
        self.blue_push_beam_setter.turn_beam_on()
    
    @kernel
    def turn_off_push_beam(self):
        self.blue_push_beam_setter.turn_beam_off()

    @kernel
    def turn_on_3d_mot_beams(self):
        self.blue_3dmot_radial_setter.turn_beam_on()
        self.blue_3dmot_axialplus_setter.turn_beam_on()
        self.blue_3dmot_axialminus_setter.turn_beam_on()

    @kernel
    def turn_off_3d_mot_beams(self):
        self.blue_3dmot_radial_setter.turn_beam_off()
        self.blue_3dmot_axialplus_setter.turn_beam_off()
        self.blue_3dmot_axialminus_setter.turn_beam_off()


