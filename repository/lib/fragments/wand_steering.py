import logging
import time

from artiq.master.scheduler import Scheduler
from ndscan.experiment import Fragment
from wand.server import ControlInterface as WANDControlInterface
from wand.tools import WLMMeasurementStatus

logger = logging.getLogger(__name__)

WAND_FAST_LOCK_POLLING = 0.5  # s


class WandSteering(Fragment):
    def build_fragment(self):
        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

    def steer_wand(
        self, laser, offset=0.0, timeout=20.0, required_accuracy=2e6, leave_locked=False
    ):
        logger.info("Setting laser %s to %.6f MHz", laser, 1e-6 * offset)
        self.wand_server.lock(laser=laser, set_point=offset, timeout=None)

        initial_laser_db = self.wand_server.get_laser_db()

        logger.info("Laser config: %s", initial_laser_db[laser])

        # Save initial settings so we can restore them at the end
        initial_gain = initial_laser_db[laser]["lock_gain"]
        initial_poll_time = initial_laser_db[laser]["lock_poll_time"]
        initial_capture_range = initial_laser_db[laser]["lock_capture_range"]

        logger.debug("Setting lock poll time = %.1fs", WAND_FAST_LOCK_POLLING)

        try:
            # Increase the poll rate and the gain with it
            self.wand_server.set_lock_params(
                laser=laser,
                gain=initial_gain * initial_poll_time / WAND_FAST_LOCK_POLLING,
                poll_time=WAND_FAST_LOCK_POLLING,
                capture_range=initial_capture_range * 10,
            )

            t_end = time.time() + timeout

            while time.time() < t_end:
                self.scheduler.pause()

                meas = self.wand_server.get_freq(laser=laser, offset_mode=True, age=1)
                status, actual_offset, _ = meas

                logger.debug(
                    "Measured laser %s, result = %s, %.1f MHz",
                    laser,
                    status,
                    1e-6 * actual_offset,
                )

                if status != WLMMeasurementStatus.OKAY:
                    continue

                if abs(offset - actual_offset) < required_accuracy:
                    logger.info("Laser %s is locked", laser)
                    break

                time.sleep(1)

        finally:
            self.wand_server.set_lock_params(
                laser=laser,
                gain=initial_gain,
                poll_time=initial_poll_time,
                capture_range=initial_capture_range,
            )
            if not leave_locked:
                self.wand_server.unlock(laser=laser, name="")

            logger.debug("Lock settings restored")
