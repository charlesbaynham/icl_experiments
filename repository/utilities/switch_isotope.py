import logging
import time
from math import isnan

from artiq.coredevice.core import Core
from ndscan.experiment import *
from ndscan.experiment.parameters import BoolParamHandle
from wand.server import ControlInterface as WANDControlInterface

from repository.lib import constants
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsFrag

logger = logging.getLogger(__name__)

TIME_TO_FAST_LOCK = 10  # s
WAND_FAST_LOCK_POLLING = 0.5  # s


class SwitchIsotopeFrag(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core
        self.setattr_fragment("set_sidebands_frag", SetEOMSidebandsFrag)
        self.set_sidebands_frag: SetEOMSidebandsFrag

        self.setattr_param(
            "sr87",
            BoolParam,
            "True = sr87, false = sr88",
            default=False,
        )
        self.sr87: BoolParamHandle
        self.set_sidebands_frag.bind_param("sr87", self.sr87)

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
            if isnan(offset):
                logger.info("Disabling lock for laser %s", laser)
                self.wand_server.unlock(laser=laser, name="")
            else:
                logger.info("Setting laser %s to %.6f MHz", laser, 1e-6 * offset)
                self.wand_server.lock(laser=laser, set_point=offset)

        initial_laser_db = self.wand_server.get_laser_db()

        laser_lock_initial_settings = []
        for laser, offset in offsets.items():
            gain = initial_laser_db[laser]["lock_gain"]
            poll_time = initial_laser_db[laser]["lock_poll_time"]
            capture_range = initial_laser_db[laser]["lock_capture_range"]
            laser_lock_initial_settings.append((laser, gain, poll_time, capture_range))

        logger.info("Setting lock poll time = %.1fs", WAND_FAST_LOCK_POLLING)

        try:
            for laser, gain, poll_time, capture_range in laser_lock_initial_settings:
                self.wand_server.set_lock_params(
                    laser=laser,
                    gain=gain,
                    poll_time=WAND_FAST_LOCK_POLLING,
                    capture_range=capture_range,
                )

            logger.info("Sleeping for %.1fs", TIME_TO_FAST_LOCK)
            time.sleep(TIME_TO_FAST_LOCK)
        finally:
            for laser, gain, poll_time, capture_range in laser_lock_initial_settings:
                self.wand_server.set_lock_params(
                    laser=laser,
                    gain=gain,
                    poll_time=poll_time,
                    capture_range=capture_range,
                )
            logger.info("Lock settings restored")

    @kernel
    def set_sidebands(self):
        self.core.break_realtime()
        self.set_sidebands_frag.set_sidebands()


SwitchIsotope = make_fragment_scan_exp(SwitchIsotopeFrag)
