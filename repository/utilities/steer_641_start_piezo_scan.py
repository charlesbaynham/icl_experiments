import logging
import time

from artiq.master.scheduler import Scheduler
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)

LASER = "641"
TOPTICA_DEVICE = "toptica_641"


class Steer641StartPiezoScanFrag(ExpFragment):
    """
    Steer the 641nm laser to a target detuning via WAND, disable WAND locking,
    then run a piezo scan on the Toptica DLCPro indefinitely. The laser is
    periodically re-steered to correct for drift. The scan is disabled on exit.
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_param(
            "detuning",
            FloatParam,
            default=0.0,
            unit="MHz",
            description="Target 641 detuning from WAND setpoint",
        )
        self.detuning: FloatParamHandle

        self.setattr_param(
            "scan_frequency",
            FloatParam,
            default=10.0,
            unit="Hz",
            min=0.1,
            description="Piezo scan frequency",
        )
        self.scan_frequency: FloatParamHandle

        self.setattr_param(
            "scan_amplitude",
            FloatParam,
            default=0.5,
            unit="V",
            min=0.0,
            description="Piezo scan amplitude (peak-to-peak voltage)",
        )
        self.scan_amplitude: FloatParamHandle

        self.setattr_param(
            "resteer_interval",
            FloatParam,
            default=600.0,
            unit="s",
            min=1.0,
            description="How often to stop the scan and re-steer via WAND",
        )
        self.resteer_interval: FloatParamHandle

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self._toptica = self.get_device(TOPTICA_DEVICE)

    def host_setup(self):
        self._toptica.open()
        return super().host_setup()

    def host_cleanup(self):
        self._toptica.close()
        return super().host_cleanup()

    def run_once(self):
        self._steer_and_start_scan()
        try:
            while True:
                t_end = time.time() + self.resteer_interval.get()
                while time.time() < t_end:
                    self.scheduler.pause()
                    time.sleep(1)
                # Re-centre: stop scan, re-steer, restart scan
                self._stop_scan()
                self._steer_and_start_scan()
        finally:
            self._stop_scan()

    def _steer_and_start_scan(self):
        logger.info(
            "Steering 641nm laser to %.3f MHz detuning", self.detuning.get() * 1e-6
        )
        self.wand_steering.steer_wand(
            LASER,
            offset=self.detuning.get(),
            timeout=20.0,
            required_accuracy=2e6,
            leave_locked=True,
        )
        logger.info("Disabling WAND lock for 641nm laser")
        self.wand_steering.wand_server.unlock(laser=LASER, name="")

        freq = self.scan_frequency.get()
        amp = self.scan_amplitude.get()
        logger.info(
            "Starting 641nm piezo scan: frequency=%.1f Hz, amplitude=%.3f V", freq, amp
        )
        laser = self._toptica.get_laser()
        laser.scan.enabled.set(False)
        laser.scan.amplitude.set(amp)
        laser.scan.frequency.set(freq)
        laser.scan.enabled.set(True)

    def _stop_scan(self):
        logger.info("Stopping 641nm piezo scan")
        self._toptica.get_laser().scan.enabled.set(False)


Steer641StartPiezoScan = make_fragment_scan_exp(Steer641StartPiezoScanFrag)
