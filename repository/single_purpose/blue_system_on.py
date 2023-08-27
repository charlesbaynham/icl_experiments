import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag

logger = logging.getLogger(__name__)


class BlueSystemOn(ExpFragment):
    """
    Load a blue 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("Blue3DMOTFrag", Blue3DMOTFrag)
        self.Blue3DMOTFrag: Blue3DMOTFrag

    @kernel
    def run_once(self):
        logger.info("Loading a blue MOT")

        self.core.break_realtime()
        self.Blue3DMOTFrag.init()
        self.core.break_realtime()
        self.Blue3DMOTFrag.load_mot(clearout=False)
        self.core.wait_until_mu(now_mu())


BlueSystemOnExp = make_fragment_scan_exp(BlueSystemOn)
