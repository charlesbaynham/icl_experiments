"""
Relock a Toptica ECDL to the cavity

This is a test script which will be incorporated into a QButler Calibration
later.

The plan based on manual fiddling is:

1. Set the ECDL to:
    FALC enabled Unlim disabled Piezo scan disabled

2. Use WAND to steer it back to 0 MHz offset (don't mess with the setpoint -
   SwitchIsotope should have made sure we're set correctly for the current EOM
   sidebands)

3. Set piezo scan enabled (10 Hz, 0.05V)

4. Set Unlim enabled

5. Set scan disabled

6 Check transmission

7. If high, done. If low, repeat from 2.
"""
import logging
import time

from artiq.master.scheduler import Scheduler
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import *
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface
from wand.tools import WLMMeasurementStatus

logger = logging.getLogger(__name__)

WAND_FAST_LOCK_POLLING = 0.5  # s


class RelockCavityFrag(Fragment):
    laser_name_wand = None
    laser_name_devicedb = None

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="cavity_relock")

        if self.laser_name_devicedb is None or self.laser_name_wand is None:
            raise TypeError(
                "You must subclass this Fragment to provide laser_name_wand and laser_name_device_db"
            )

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_param(
            "piezo_scan_amplitude",
            FloatParam,
            default=0.05,
            unit="V",
            min=0,
            description="Piezo scan amplitude during relock",
        )
        self.piezo_scan_amplitude: FloatParamHandle

        self.setattr_param(
            "piezo_scan_frequency",
            FloatParam,
            default=10,
            unit="Hz",
            min=0,
            description="Piezo scan frequency during relock",
        )
        self.piezo_scan_frequency: FloatParamHandle

        self.setattr_param(
            "delay_before_unlim",
            FloatParam,
            default=0.1,
            unit="ms",
            min=0,
            description="Delay before engaging unlim",
        )
        self.delay_before_unlim: FloatParamHandle

        self.setattr_param(
            "delay_after_unlim",
            FloatParam,
            default=0.2,
            unit="ms",
            min=0,
            description="Delay after engaging unlim before disabling scan",
        )
        self.delay_after_unlim: FloatParamHandle

        self.setattr_param(
            "max_attempts",
            IntParam,
            default=3,
            min=1,
            description="Max number of relock attempts",
        )
        self.max_attempts: IntParamHandle

        self.setattr_param(
            "lock_detection_threshold",
            FloatParam,
            default=10e6,
            unit="MHz",
            min=0,
            description="Wavemeter threshold for lock detection",
        )
        self.lock_detection_threshold: FloatParamHandle

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.toptica_controller: TopticaDLCPro = self.get_device(
            self.laser_name_devicedb
        )

    def host_setup(self):
        self.toptica_controller.open()
        return super().host_setup()

    def host_cleanup(self):
        self.toptica_controller.close()
        return super().host_cleanup()

    def relock(self):
        attempts = 0

        while not self.is_cavity_locked():
            attempts += 1
            if attempts >= self.max_attempts.get():
                raise RuntimeError("Max attempts reached and cavity is still unlocked")

            self.set_piezo_scan(enabled=False)
            self.set_FALC(main=False, unlim=False)

            self.steer_wand(laser=self.laser_name_wand, offset=0.0, timeout=20)

            self.set_piezo_scan(
                enabled=True,
                amplitude=self.piezo_scan_amplitude.get(),
                frequency=self.piezo_scan_frequency.get(),
            )
            self.set_FALC(main=True, unlim=False)

            time.sleep(self.delay_before_unlim.get())

            self.set_FALC(main=True, unlim=True)

            time.sleep(self.delay_after_unlim.get())

            self.set_piezo_scan(enabled=False)

        logger.info("Relock successful!")

    def set_piezo_scan(self, enabled=False, amplitude=0.0, frequency=1.0):
        logger.debug(
            "set_piezo_scan, enabled=%s, amplitude=%s, frequency=%s",
            enabled,
            amplitude,
            frequency,
        )
        self.toptica_controller.get_laser().scan.enabled.set(False)
        self.toptica_controller.get_laser().scan.amplitude.set(amplitude)
        self.toptica_controller.get_laser().scan.frequency.set(frequency)
        self.toptica_controller.get_laser().scan.enabled.set(enabled)

    def set_FALC(self, main=False, unlim=False):
        logger.debug("set_FALC, main=%s, unlim=%s", main, unlim)
        falc = self.toptica_controller.get_falc()

        falc.main.enabled.set(main)
        falc.unlim.enabled.set(unlim)

    def steer_wand(self, laser, offset=0.0, timeout=20.0, required_accuracy=2e6):
        logger.info("Setting laser %s to %.6f MHz", laser, 1e-6 * offset)
        self.wand_server.lock(laser=laser, set_point=offset, timeout=timeout)

        initial_laser_db = self.wand_server.get_laser_db()

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
            self.wand_server.unlock(laser=laser, name="")

            logger.debug("Lock settings restored")

    def is_cavity_locked(self):
        logger.warn(
            "Cavity transmission detection not implemented yet! Using the wavemeter instead"
        )

        meas = self.wand_server.get_freq(
            laser=self.laser_name_wand, offset_mode=True, age=1
        )
        status, actual_offset, _ = meas

        if status != WLMMeasurementStatus.OKAY:
            raise RuntimeError("Wavemeter check failed")

        locked = abs(actual_offset) < self.lock_detection_threshold.get()

        logger.debug("Cavity lock status: %s", locked)

        return locked


class Relock689Frag(RelockCavityFrag, ExpFragment):
    laser_name_wand = "689"
    laser_name_devicedb = "toptica_689"

    def run_once(self) -> None:
        self.relock()


class Relock698Frag(RelockCavityFrag, ExpFragment):
    laser_name_wand = "698"
    laser_name_devicedb = "toptica_698"

    def run_once(self) -> None:
        self.relock()


Relock689Cavity = make_fragment_scan_exp(Relock689Frag)
Relock698Cavity = make_fragment_scan_exp(Relock698Frag)
