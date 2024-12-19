import logging
import time

from artiq.coredevice.core import Core
from artiq.master.scheduler import Scheduler
from ndscan.experiment import BoolParam
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment import rpc
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from wand.server import ControlInterface as WANDControlInterface
from wand.tools import WLMMeasurementStatus

from repository.lib import constants
from repository.lib.fragments.set_eom_sidebands import SetAllEOMSidebandsFrag

logger = logging.getLogger(__name__)

MAX_TIME_TO_FAST_LOCK = 60  # s
MAX_FINAL_OFFSET = 5e6  # Hz
WAND_FAST_LOCK_POLLING = 0.5  # s


class SwitchIsotopeFrag(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_fragment("set_sidebands_frag", SetAllEOMSidebandsFrag)
        self.set_sidebands_frag: SetAllEOMSidebandsFrag

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

        self.detuning_param_handles = {}
        for laser, (_, locked) in constants.WAND_SETPOINTS_87.items():
            if locked:
                p: FloatParamHandle = self.setattr_param(
                    f"detuning_{laser}",
                    FloatParam,
                    description=f"Detuning of laser {laser}",
                    default=0.0,
                    unit="MHz",
                )
                self.detuning_param_handles[laser] = p

    @kernel
    def run_once(self) -> None:
        self.set_sidebands()
        self.steer_wand()

    @rpc
    def steer_wand(self):
        if self.sr87.get():
            setpoints = constants.WAND_SETPOINTS_87
        else:
            setpoints = constants.WAND_SETPOINTS_88

        for laser, (setpoint, lock_enabled) in setpoints.items():
            if lock_enabled:
                detuning = self.detuning_param_handles[laser].get()
            else:
                detuning = 0

            logger.info(
                "Setting laser %s reference frequency to %.0f THz",
                laser,
                setpoint * 1e-12,
            )
            self.wand_server.set_reference_freq(laser=laser, f_ref=setpoint)

            if not lock_enabled:
                logger.info("Disabling lock for laser %s", laser)
                try:
                    self.wand_server.unlock(laser=laser, name="")
                except (ValueError, KeyError):
                    # Raised if this laser has no controller - fine, since we don't want it locked anyway!
                    pass
            else:
                logger.info(
                    "Setting laser %s to %.2f MHz",
                    laser,
                    detuning * 1e-6,
                )
                self.wand_server.lock(laser=laser, set_point=detuning, timeout=None)

        initial_laser_db = self.wand_server.get_laser_db()

        laser_lock_initial_settings = []
        for laser, (_, lock_enabled) in setpoints.items():
            if lock_enabled:
                gain = initial_laser_db[laser]["lock_gain"]
                poll_time = initial_laser_db[laser]["lock_poll_time"]
                capture_range = initial_laser_db[laser]["lock_capture_range"]
                laser_lock_initial_settings.append(
                    (laser, gain, poll_time, capture_range)
                )

        logger.info("Setting lock poll time = %.1fs", WAND_FAST_LOCK_POLLING)

        try:
            # Save initial settings so we can restore them at the end
            for laser, gain, poll_time, capture_range in laser_lock_initial_settings:
                self.wand_server.set_lock_params(
                    laser=laser,
                    gain=gain
                    * poll_time
                    / WAND_FAST_LOCK_POLLING,  # Increase gain by the increased poll rate
                    poll_time=WAND_FAST_LOCK_POLLING,
                    capture_range=capture_range * 10,
                )

            # Start by assuming that all the lasers we want to be locked are
            # currently unlocked. We'll check each until it's within
            # MAX_FINAL_OFFSET of setpoint, or the time runs out
            laser_unlocked = {
                l: lock_enabled for l, (_, lock_enabled) in setpoints.items()
            }

            t_end = time.time() + MAX_TIME_TO_FAST_LOCK
            while any(laser_unlocked.values()) and time.time() < t_end:
                logger.debug("laser_unlocked = %s", laser_unlocked)

                for laser, unlocked in laser_unlocked.items():
                    self.scheduler.pause()
                    if unlocked:
                        desired_offset = self.detuning_param_handles[laser].get()
                        meas = self.wand_server.get_freq(
                            laser=laser, offset_mode=True, age=1
                        )
                        status, actual_offset, _ = meas

                        logger.debug(
                            "Measured laser %s, result = %s, %.1f MHz",
                            laser,
                            status,
                            1e-6 * actual_offset,
                        )

                        if status != WLMMeasurementStatus.OKAY:
                            continue

                        if abs(desired_offset - actual_offset) < MAX_FINAL_OFFSET:
                            logger.info("Laser %s is locked", laser)
                            laser_unlocked[laser] = False

                time.sleep(1)

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
