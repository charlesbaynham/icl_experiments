import logging
import socket
import struct

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


def _get_pump_current(ip):
    UDP_PORT = 2527

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)

    # Send a read-all request
    req = b"\x01\x05"
    #         |   |
    #         |   |--> Protocol version (see User Manual)
    #         |------> Command (see User Manual)
    sock.sendto(req, (ip, UDP_PORT))

    # Receive only the meaningful part of Sip Power answer (first 42 bytes of 102)
    data, addr = sock.recvfrom(42)

    # Parse binary answer and print it
    pdata = struct.unpack("!xxHHHIIHHxxHHIIHBBI", data)

    labels = [
        "card type",
        "hw_code",
        "sw_version",
        "serial number",
        "iout",
        "vout",
        "vin",
        "temperature",
        "arcing number",
        "life time",
        "ontime",
        "status",
        "sw_status",
        "reset cause",
        "uptime",
    ]
    ddata = dict(zip(labels, pdata))

    logger.debug("raw data: %s", ddata)

    status = ddata["status"]

    if status:
        # Pump is reporting current in nA
        return ddata["iout"] * 1e-9
    else:
        # Pump is off or in error state
        return -1.0


def _get_pump_pressure(
    ip,
    conversion_rate=65
    / 1.333e-3,  # 65 A/Torr is the default according to p22 of the manual
):
    """
    Return the pump pressure in bar
    """
    current = _get_pump_current(ip)

    if current == -1.0:
        # The pump is off
        logger.debug("Pump at %s is off or in error state", ip)
        return -1.0

    pressure = current / conversion_rate
    logger.debug("Pressure = %s", pressure)

    return max([pressure, 1e-14])  # Cannot resolve below 1e-11 mbar


class _MonitorSAESIonPumpBase(Calibration):
    """
    Monitor the current and pressure of a SAES SIP Power ion pump
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
        pressure = _get_pump_pressure(self.ip)

        return CalibrationResult.OK, {
            "tags": {"sensor": self.description, "type": "pressure"},
            "fields": {"pressure": 1e3 * pressure},  # Convert to mbar
        }


class MonitorClockCh1IonPump(_MonitorSAESIonPumpBase):
    ip = "clock-ionpump-ch1.usl"
    description = "clock_ch1"


class MonitorClockCh2IonPump(_MonitorSAESIonPumpBase):
    ip = "clock-ionpump-ch2.usl"
    description = "clock_ch2"
