## %
# This is a terrible script to hackily grab the temperature from the monitor. We'll write a better one later.
import logging
import time

import requests
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import StringValue
from artiq.language.core import TerminationRequested
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController

logger = logging.getLogger(__name__)


class MonitorLabTemperature(EnvExperiment):
    """
    Monitor the temperature of the lab
    """

    def build(self):
        self.setattr_argument(
            "monitor_url", StringValue(default="http://192.168.1.3/temp1.txt")
        )
        self.setattr_argument("description", StringValue(default="above_chamber"))
        self.setattr_argument(
            "delay", NumberValue(default=30, scale=1, step=1, ndecimals=0)
        )

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.set_default_scheduling(pipeline_name=f"temperature")

    def run(self):
        while True:
            try:
                temp_str = requests.get(self.monitor_url).text
                temperature = float(temp_str)

                logger.debug('Temperature = %f ("%s")', temperature, temp_str)

                self.influx_logger.write(
                    tags={"type": "temperature", "sensor": self.description},
                    fields={"value": temperature},
                )

                self.scheduler.pause()
                time.sleep(self.delay)

            except Exception as e:
                if isinstance(e, (KeyboardInterrupt, TerminationRequested)):
                    break
                else:
                    logger.error("Error occured:", exc_info=e)
                    if self.scheduler.check_pause():
                        return
