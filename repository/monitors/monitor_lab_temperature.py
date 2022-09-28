import logging
import time

import requests
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import StringValue
from artiq.language.core import TerminationRequested
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController

from ndscan.experiment import StringParam

from qbutler.calibration import Calibration, CalibrationResult

logger = logging.getLogger(__name__)


class MonitorLabTemperature(Calibration):
    """
    Monitor the temperature of the lab
    """

    def build_calibration(self):
        self.setattr_argument(
            "monitor_url", StringValue(default="http://192.168.1.3/temp1.txt")
        )
        self.setattr_argument("description", StringValue(default="above_chamber"))
        self.set_timeout(30)

    def run(self):
        temp_str = requests.get(self.monitor_url).text
        temperature = float(temp_str)

        logger.debug('Temperature = %f ("%s")', temperature, temp_str)

        self.status.push(CalibrationResult.OK)
        self.data.push(temperature)
