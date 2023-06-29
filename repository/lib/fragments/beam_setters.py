import logging
from typing import List
from typing import Optional

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam

import repository.lib.constants as constants

logger = logging.getLogger(__name__)


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of suservoed beams, possibly with shutters, to their default
    settings

    To use this fragment you must subclass it and provide a class attribute
    "beam_infos" which is a list of :class:`pyaion.models.SUServoedBeam`
    objects describing the beams that this class instance will control.
    """

    kernel_invariants = {"max_shutter_delay"}

    beam_infos: List[SUServoedBeam] = None  # type: ignore

    def build_fragment(self):
        if self.beam_infos is None:
            raise TypeError(
                "You must create a subclass of SetBeamsToDefaults to use it - see the documentation"
            )

        self.setattr_device("core")
        self.core: Core

        self.suservo_setters: List[LibSetSUServoStatic] = []

        self.ttls: List[TTLOut] = []

        for beam_info in self.beam_infos:
            self.setattr_fragment(
                beam_info.name, LibSetSUServoStatic, beam_info.suservo_device
            )
            self.suservo_setters.append(getattr(self, beam_info.name))
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
        for i in range(len(self.beam_infos)):
            setter = self.suservo_setters[i]
            beam_info = self.beam_infos[i]

            setter.set_suservo(
                float(beam_info.frequency), 1.0, float(beam_info.attenuation)
            )

        for ttl in self.ttls:
            ttl.set_o(shutter_state)
