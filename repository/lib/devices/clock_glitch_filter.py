import logging
from unittest.mock import MagicMock

from generic_scpi_driver import GenericDriver

logger = logging.getLogger(__name__)


class ClockGlitchFilter(GenericDriver):
    pass


ClockGlitchFilter._register_query("get_identity", "*IDN")
ClockGlitchFilter._register_query("get_version", "*VER")
ClockGlitchFilter._register_query("get_num_glitches", "*NUM?")


# Parse configuration strings in the format "GLITCH: xxx.xx, GATE: xxx.xx"
def string_to_config(config_string: str):
    config_dict = {}
    parts = config_string.split(", ")
    for part in parts:
        key, value = part.split(": ")
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
