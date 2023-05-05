import logging
import re

from artiq.coredevice.core import Core
from artiq.experiment import kernel, now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp


import repository.lib.constants as constants
from repository.lib.fragments.beam_setter import SetBeamsToDefaults

logger = logging.getLogger(__name__)

# Get all the beams from constants whose name begins with "blue_"
BLUE_BEAMS = [k for k in constants.AOM_BEAMS.keys() if re.match(r"^blue_", k)]


class BlueSystemOn(ExpFragment):
    """
    Turn the blue system AOMs and shutters on to their default settings
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("SetBeamsToDefaults", SetBeamsToDefaults, beams_to_enable=BLUE_BEAMS)
        self.SetBeamsToDefaults: SetBeamsToDefaults
        

    @kernel
    def run_once(self):
        logger.info("Enabling AOMS:")
        logger.info(BLUE_BEAMS)

        self.core.break_realtime()
        self.SetBeamsToDefaults.turn_on_all()
        self.core.wait_until_mu(now_mu())


BlueSystemOnExp = make_fragment_scan_exp(BlueSystemOn)
