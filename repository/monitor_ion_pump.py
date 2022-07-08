import logging
import re
import time
from telnetlib import Telnet

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import StringValue
from artiq.language.core import TerminationRequested
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController

logger = logging.getLogger(__name__)

COMMAND_PRESSURE = b"spc 0b 1\r\n"
COMMAND_CURRENT = b"spc 0a 1\r\n"


class MonitorIonPump(EnvExperiment):
    """
    Monitor the current / pressure of an ion pump
    """

    def build(self):
        self.setattr_argument("ip", StringValue(default="192.168.0.43"))
        self.setattr_argument(
            "delay", NumberValue(default=30, scale=1, step=1, ndecimals=0)
        )

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

    def run(self):

        while True:

            try:
                with Telnet(self.ip, 23) as tn:
                    logger.debug("Connected to ion pump at %s", self.ip)

                    tn.read_until(b">")

                    logger.debug("Querying ion pump pressure at %s", self.ip)

                    tn.write(COMMAND_PRESSURE)
                    response = tn.read_until(b">", 1)

                    logger.debug("Response = %s", response)

                    pressure = float(
                        re.match(r"OK 00 ([\d\.E-]{7}) MBA.*", response.decode())[1]
                    )

                    logger.debug("Querying ion pump current at %s", self.ip)

                    tn.write(COMMAND_CURRENT)
                    response = tn.read_until(b">", 1)

                    logger.debug("Response = %s", response)

                    current = float(
                        re.match(r"OK 00 ([\d\.E-]{7}) AMPS.*", response.decode())[1]
                    )

                    self.debug(
                        "Writing pressure = %s, current = %s to database",
                        pressure,
                        current,
                    )

                    self.influx_logger.write(
                        tags={"type": "ion_pump"},
                        fields={"pressure": pressure, "current": current},
                    )

                    self.scheduler.pause()
                    time.sleep(self.delay)

            except Exception as e:
                if isinstance(e, (KeyboardInterrupt, TerminationRequested)):
                    pass
                else:
                    logger.error("Error occured:", exc_info=e)
