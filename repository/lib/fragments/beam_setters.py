import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of suservoed beams, possibly with shutters, to their default settings
    """

    kernel_invariants = {"max_shutter_delay"}

    def build_fragment(self, beams_to_enable: List[str]):
        self.beams_to_enable = beams_to_enable

        self.setattr_device("core")
        self.core: Core

        self.suservo_setters: List[LibSetSUServoStatic] = []
        self.beam_infos = [constants.AOM_BEAMS[beam] for beam in self.beams_to_enable]
        self.ttls: List[TTLOut] = []

        for beam, beam_info in zip(self.beams_to_enable, self.beam_infos):
            self.setattr_fragment(beam, LibSetSUServoStatic, beam_info.suservo_device)
            self.suservo_setters.append(getattr(self, beam))
            if beam_info.shutter_device:
                self.ttls.append(self.get_device(beam_info.shutter_device))

        self.max_shutter_delay = max(
            [beam_info.shutter_delay for beam_info in self.beam_infos]
        )

    @portable
    def get_max_shutter_delay(self):
        return self.max_shutter_delay

    @kernel
    def turn_on_all(self, shutter_state=True):
        """
        Turn on the pre-configured beams to their default values

        If `sw_state == False`, turn on the AOMs but turn off the shutters.

        This method does not advance the timeline and does not respect
        shutter delays - it just turns everything on immediately.
        """
        for i in range(len(self.beams_to_enable)):
            setter = self.suservo_setters[i]
            beam_info = self.beam_infos[i]

            setter.set_suservo(
                float(beam_info.frequency), 1.0, float(beam_info.attenuation)
            )

        for ttl in self.ttls:
            ttl.set_o(shutter_state)
