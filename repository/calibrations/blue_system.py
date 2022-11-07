import logging

from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.experiment import RTIOUnderflow
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


class BlueInjectionAOM(Calibration):
    """
    Ensure that the double-pass AOM which injects the blue diodes has been set
    up and turned on
    """

    def build_calibration(self):
        self.setup_completed = False

        self.setattr_device("core")
        self.suservo_injection_aom: Channel = self.get_device("suservo_injection_aom")

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        try:
            self.suservo_injection_aom.servo.init()
        except RTIOUnderflow:
            self.core.break_realtime()
            self.suservo_injection_aom.servo.init()

    @portable
    def run_once(self):
        if self.setup_completed:
            self.status.push(CalibrationResult.OK)
        else:
            self.status.push(CalibrationResult.BAD_EXPIRED)

        self.data.push(None)

    def fix_own_state(self):
        self.setup_completed = True

        # TODO: turn on the AOM here
        raise NotImplementedError
