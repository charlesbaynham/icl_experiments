import logging
import re
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


SUSERVOED_BEAMS = [k for k in constants.AOM_BEAMS.keys() if re.match(r"^blue_", k)]


class BlueSystemOn(ExpFragment):
    """
    Turn the blue system AOMs and shutters on to default settings
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.suservo_setters: List[LibSetSUServoStatic] = []
        self.beam_info = [constants.AOM_BEAMS[beam] for beam in SUSERVOED_BEAMS]
        self.ttls: List[TTLOut] = []

        for beam, beam_info in zip(SUSERVOED_BEAMS, self.beam_info):
            self.setattr_fragment(beam, LibSetSUServoStatic, beam_info.suservo_device)
            self.suservo_setters.append(getattr(self, beam))
            if beam_info.shutter_device:
                self.ttls.append(self.get_device(beam_info.shutter_device))

        self.setattr_device("core")

    @kernel
    def run_once(self):
        logger.info("Enabling AOMS:")
        logger.info(SUSERVOED_BEAMS)

        self.core.break_realtime()
        self.turn_on()

    @kernel
    def turn_on(self):
        # Set the outputs
        for i in range(len(SUSERVOED_BEAMS)):
            setter = self.suservo_setters[i]
            beam_info = self.beam_info[i]

            setter.set_suservo(
                float(beam_info.frequency), 1.0, float(beam_info.attenuation)
            )

        for ttl in self.ttls:
            ttl.on()


BlueSystemOnExp = make_fragment_scan_exp(BlueSystemOn)
