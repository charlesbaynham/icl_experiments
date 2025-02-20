import logging
import re
from telnetlib import Telnet

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)

COMMAND_PRESSURE = b"spc 0b 1\r\n"
COMMAND_CURRENT = b"spc 0a 1\r\n"


class _MonitorIonPumpBase(Calibration):
    """
    Monitor the current and pressure of an ion pump
    """

    ip = None
    description = None

    def build_calibration(self):
        self.set_timeout(30)

        if self.ip is None:
            raise TypeError("IP address of ion pump not set")

        if self.description is None:
            raise TypeError("Description of ion pump not set")

    def check_own_state(self):
        with Telnet(self.ip, 23) as tn:
            logger.debug("Connected to ion pump at %s", self.ip)

            tn.read_until(b">", timeout=1)

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

            logger.debug(
                "Reporting pressure = %s, current = %s",
                pressure,
                current,
            )

            return CalibrationResult.OK, {
                "tags": {"sensor": self.description, "type": "pressure"},
                "fields": {"pressure": pressure, "current": current},
            }


class MonitorAIONCh1IonPump(_MonitorIonPumpBase):
    ip = "10.137.1.8"
    description = "chamber1"


class MonitorAIONCh2IonPump(_MonitorIonPumpBase):
    ip = "10.137.1.16"
    description = "chamber2"
