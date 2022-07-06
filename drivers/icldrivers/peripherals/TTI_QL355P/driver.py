"""
TTI_QL355P driver
=================

A demonstration driver for a TTI current supply. These supplies work by sending
and receiving SCPI commands over a serial connection, as many device do. Since
this is such a common pattern, this driver uses the `Generic SCPI driver
<https://gitlab.com/charlesbaynham/generic_scpi_driver.git>`_ to control them.

This driver is probably fully fledged enough to merit its own repository, but I
have included it here as an example. It could be used as a local driver (by
initiating the `TTIPowerSupply`) object, or as a controller (via
`aqctl_TTIPowerSupply`). Note that it also contains unit tests, stored in the
`tests` directory, which make use of simulation mode via `SimTTI`.
"""
import logging
import math
import re

from generic_scpi_driver import GenericDriver
from generic_scpi_driver import with_handler
from generic_scpi_driver import with_lock

from .sim_TTI import SimTTI

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MIN_CURRENT = 0.0001


class TTIPowerSupply(GenericDriver):
    """
    Driver for a TTI QL355P power supply. Communicates over RS232 with an exclusive VISA lock.
    """

    _tol = 1e-5

    def __init__(self, *args, **kwargs):
        # kwargs["wait_after_connect"] = 1
        kwargs["baud_rate"] = 19200
        kwargs["read_termination"] = "\r\n"
        kwargs["write_termination"] = "\r\n"

        super(TTIPowerSupply, self).__init__(*args, **kwargs)

    @with_handler
    @with_lock
    def set_check_voltage(self, v):
        """
        Sets the voltage, then reads it to confirm success
        :param v:
        """
        self.set_voltage(v)
        v_out = self.get_voltage()
        if abs(v - v_out) > self._tol:
            raise RuntimeError(
                "Failure to write voltage. Asked for {}, got {}".format(v, v_out)
            )

    @with_handler
    @with_lock
    def set_current(self, curr):
        if not math.isfinite(curr):
            raise ValueError('Invalid current "{}"'.format(curr))

        if curr == 0:
            self.disable()
            self.instr.write("i1 {:.5f}".format(MIN_CURRENT))
        elif curr < 0.0001:
            raise ValueError("Current must be > {} mA".format(1e3 * MIN_CURRENT))
        else:
            self.instr.write("i1 {:.5f}".format(curr))
            self.enable()

    def get_output_state(self):
        raise NotImplementedError(
            "Sorry, the TTi QL355P has no way of reading this setting."
        )

    def enable(self):
        self.set_output_state(True)

    def disable(self):
        self.set_output_state(False)

    @with_handler
    @with_lock
    def set_check_current(self, curr):
        # Round to 0.1mA - the device's precision
        curr = round(curr, 4)

        self.set_current(curr)
        if curr != 0:
            I_out = self.get_current()
            logger.debug("Current = {}, asked for = {}".format(I_out, curr))
            if abs(curr - I_out) > self._tol:
                raise RuntimeError(
                    "Failure to write current. Asked for {}, got {}".format(curr, I_out)
                )
        # If the current is set to 0, the device will be disabled. The TTI isn't
        # capable of reporting this to us, so we can't check.

    def set_check_current_range(self, range: str):
        range = range.upper()
        self.set_current_range(range)
        r = self.get_current_range()
        if not r == range:
            raise RuntimeError('Error setting range "{}"'.format(range))

    @staticmethod
    def _parse_from_current_range(range: str):
        if not isinstance(range, str):
            raise TypeError('Range must be "LOW", "MED" or "HIGH"')

        range = range.upper()

        if range not in ["LOW", "MED", "HIGH"]:
            raise ValueError('Range must be "LOW", "MED" or "HIGH"')

        if range == "HIGH":
            return "0"
        elif range == "MED":
            return "1"
        else:
            return "2"

    @staticmethod
    def _parse_to_current_range(mode: str):
        try:
            # This regex is designed to match both old and new version of the firmware.
            # Old versions return e.g. "R1 1" whereas new ones just return "1"
            mode = re.match(r"^(?:R\d )?(\d+)", mode.strip())[1]

            if mode == "0":
                return "HIGH"
            elif mode == "1":
                return "MED"
            elif mode == "2":
                return "LOW"
            else:
                raise RuntimeError('Could not parse response "{}"'.format(mode))
        except TypeError:
            pass

    @staticmethod
    def _check_and_format_voltage(v):
        if not math.isfinite(v):
            raise ValueError('Invalid voltage "{}"'.format(v))
        return format(v, ".5f")


TTIPowerSupply._register_simulator(SimTTI)

TTIPowerSupply._register_query(
    "get_identity",
    "*IDN?",
    response_parser=str,
)


TTIPowerSupply._register_query(
    "reset",
    "*RST",
    response_parser=None,
)


TTIPowerSupply._register_query(
    "set_current_range",
    "range1",
    response_parser=None,
    args=[
        GenericDriver.Arg(
            name="range", validator=TTIPowerSupply._parse_from_current_range
        )
    ],
)

TTIPowerSupply._register_query(
    "get_current_range",
    "range1?",
    response_parser=TTIPowerSupply._parse_to_current_range,
)


TTIPowerSupply._register_query(
    "get_current",
    "i1?",
    response_parser=lambda r: float(r.split(" ")[1]),
)

TTIPowerSupply._register_query(
    "set_output_state",
    "OP1",
    response_parser=None,
    args=[
        GenericDriver.Arg(name="state", validator=lambda state: "1" if state else "0")
    ],
)


TTIPowerSupply._register_query(
    "set_voltage",
    "v1",
    response_parser=None,
    args=[
        GenericDriver.Arg(
            name="voltage", validator=TTIPowerSupply._check_and_format_voltage
        )
    ],
)

TTIPowerSupply._register_query(
    "get_voltage",
    "v1?",
    response_parser=lambda r: float(r.split(" ")[1]),
)
