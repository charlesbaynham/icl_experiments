import logging

from artiq.coredevice.core import Core
from ndscan.experiment import *
from ndscan.experiment.parameters import BoolParamHandle
from wand.server import ControlInterface as WANDControlInterface

from repository.lib import constants
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsFrag

logger = logging.getLogger(__name__)

WAND_DEFAULT_LOCK_POLLING = 10.0  # s
WAND_FAST_LOCK_POLLING = 0.5  # s


class SwitchIsotopeFrag(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core
        self.setattr_fragment("set_sidebands_frag", SetEOMSidebandsFrag)
        self.set_sidebands_frag: SetEOMSidebandsFrag

        self.setattr_param_like("sr87", self.set_sidebands_frag)
        self.sr87: BoolParamHandle

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

    def run_once(self) -> None:
        self.steer_wand()
        self.set_sidebands()

    def steer_wand(self):
        if self.sr87.get():
            offsets = constants.WAND_OFFSETS_87
        else:
            offsets = constants.WAND_OFFSETS_88

        for laser, offset in offsets.items():
            logger.info("Setting laser %s to %.6f MHz", laser, 1e-6 * offset)
            self.wand_server.lock(laser=laser, set_point=offset)

        print(self.wand_server.get_laser_db())

    @kernel
    def set_sidebands(self):
        self.core.break_realtime()
        self.set_sidebands_frag.set_sidebands()


SwitchIsotope = make_fragment_scan_exp(SwitchIsotopeFrag)
