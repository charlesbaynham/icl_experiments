import logging
from unittest.mock import MagicMock

from generic_scpi_driver import GenericDriver
from generic_scpi_driver.session import Session
from generic_scpi_driver.visa_session import get_com_port_by_hwid
from serial import Serial

logger = logging.getLogger(__name__)


class _RawSerialInstance(Session):
    def __init__(self, id, **kwargs):
        id_resolved = get_com_port_by_hwid(id)
        logger.debug("Resolved serial port ID %s to %s", id, id_resolved)
        self.ser = Serial(id_resolved, 115200, timeout=1)

    def close(self):
        self.ser.close()
        self.ser = None

    def flush(self, *args, **kwargs):
        pass

    def write(self, msg):
        """Send a message without waiting for a reply"""
        if self.ser is None:
            raise RuntimeError("This controller has been closed")

        self.ser.write(b"%s\n" % msg.encode())

    def query(self, msg):
        """Send a message and return the reply"""
        self.write(msg)

        # This device repeats the command before it replies for some reason,
        # so ignore the first line
        # _ = self.ser.readline()
        line = self.ser.readline()
        rtn = line.decode().strip()
        return rtn

    def read_line(self):
        line = self.ser.readline()
        return line.decode()


class ClockGlitchFilter(GenericDriver):
    session_factory = _RawSerialInstance

    def ping(self):
        self.get_identity()


ClockGlitchFilter._register_query("get_identity", "*IDN")
ClockGlitchFilter._register_query("get_version", "*VER")
ClockGlitchFilter._register_query("get_num_glitches", "*NUM?")


# Parse configuration strings in the format "GLITCH=xxx.xx, GATE=xxx.xx"
def string_to_config(config_string: str):
    logger.debug("Parsing config string: %s", config_string)
    config_dict = {}
    parts = config_string.split(",")
    for part in parts:
        key, value = part.split("=")
        config_dict[key.strip()] = value.strip()
    return config_dict


ClockGlitchFilter._register_query("get_config", "CONF?", response_parser=string_to_config)  # type: ignore
ClockGlitchFilter._register_query(
    "set_config",
    "CONF",
    response_parser=string_to_config,
    args=[
        GenericDriver.Arg(
            name="glitch_threshold",
            default=0.2,
            validator=float,
        ),
        GenericDriver.Arg(
            name="gate_threshold",
            default=2.0,
            validator=float,
        ),
    ],
)

ClockGlitchFilter._register_query("read_voltages", "READ?", response_parser=string_to_config)  # type: ignore


class MockClockGlitchFilter:
    def __init__(self, *args, **kwargs):
        self.get_identity = MagicMock(return_value="Mock Clock Glitch Filter")
        self.get_version = MagicMock(return_value="abcdef")
        self.get_num_glitches = MagicMock(return_value=0)
        self.get_config = MagicMock(
            return_value={
                "GLITCH": "0.2",
                "GATE": "2.0",
            }
        )
        self.set_config = MagicMock(
            return_value={
                "GLITCH": "0.2",
                "GATE": "2.0",
            }
        )
