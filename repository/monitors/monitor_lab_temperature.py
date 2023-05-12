import logging

import requests
from ndscan.experiment import StringParam
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


class MonitorLabTemperature(Calibration):
    """
    Monitor the temperature of the lab
    """

    def build_calibration(self):
        self.setattr_param(
            "monitor_url",
            StringParam,
            "URL to access",
            default='"http://192.168.1.3/temp1.txt"',
        )
        self.setattr_param(
            "description",
            StringParam,
            "Sensor description",
            default='"above_chamber"',
        )

        self.set_timeout(30)

    def check_own_state(self):
        temp_str = requests.get(self.monitor_url.get()).text
        temperature = float(temp_str)

        logger.debug('Temperature = %f ("%s")', temperature, temp_str)

        return CalibrationResult.OK, {
            "tags": {"sensor": self.description.get()},
            "fields": {"value": temperature},
        }
