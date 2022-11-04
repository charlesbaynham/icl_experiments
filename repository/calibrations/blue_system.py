import logging

import requests
from artiq.coredevice.suservo import Channel
from ndscan.experiment import Fragment
from ndscan.experiment import StringParam
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


class BlueInjectedDiode(Calibration):
    """
    Calibration for ensuring a blue diode is injected
    """

    def build_calibration(self):
        pass

    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Ensure AOM is on and active
        self.aom_suservo_channel: Channel

        self.aom_suservo_channel

    def run_once(self):
        pass
