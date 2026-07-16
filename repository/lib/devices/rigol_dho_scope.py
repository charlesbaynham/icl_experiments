import numpy as np
from generic_scpi_driver.driver import GenericDriver
from generic_scpi_driver.session import Session
from pyvisa import ResourceManager
from pyvisa.resources import Resource


class VisaSession(Session):
    def __init__(self, id: str, **kwargs) -> None:
        self._id = id
        self.session: Resource = ResourceManager().open_resource(self._id)

    def write(self, s: str) -> None:
        """
        Send a string to the device but do not expect a response
        """
        self.session.write(s)

    def query(self, s: str) -> str:
        """
        Send a string to the device and expect a string response
        """
        return self.session.query(s)

    def close(self) -> None:
        """
        Terminate communication with the device

        This Session will not be used again after calling close: this method
        should clean up any resources used, e.g. closing connections.
        """
        self.session.close()


class RigolDHO(GenericDriver):

    session_factory = VisaSession

    def __init__(self, *args, id: str, simulation: bool = False, **kwargs):
        super().__init__(self, *args, id=id, simulation=simulation, **kwargs)

    def set_vertscale(self, channel: int, scale: float):
        self.instr.write(f":chan{channel:d} {scale:.3f}")
        checkval = self.instr.query(f":chan{channel:d}?")
        if not np.isclose(float(checkval), scale):
            raise RuntimeError()

    def set_trigger_source(self, type: str, source: str):
        self.instr.write(f":TRIG:{type}:SOUR {source}")
        # Need a check but screw this!

    def set_trigger_level(self, type: str, level: float):
        self.instr.write(f":TRIG:{type}:LEV {level}")
        # Need a check but screw this!

    def get_waveform(self, data_type: str):
        self.instr.write(f":WAV:MODE MAX")
        # I will assume we want all the data, this will defualt to normal or max depending on whether
        # the scope is stopped
        self.instr.write(f":WAV:FORM {data_type}")
        response = self.instr.query(":WAV:DATA?")
        return response


RigolDHO._register_query("get_identity", "*IDN?", response_parser=str)

RigolDHO._register_query("reset", "*RST", response_parser=None)

RigolDHO._register_query("stop", "STOP", response_parser=None)

RigolDHO._register_query("run", "RUN", response_parser=None)

RigolDHO._register_query("clear", "CLE", response_parser=None)

RigolDHO._register_query("single", "SING", response_parser=None)

RigolDHO._register_query("opc", "*OPC?", response_parser=int)

RigolDHO._register_query("force_trigger", "TFOR", response_parser=None)

RigolDHO._register_query("get_horizontal_ref", "TIM:HREF:POS?", response_parser=str)

RigolDHO._register_query(
    "trigger_mode",
    "TRIG:SWE",
    response_parser=None,
    args=[
        GenericDriver.Arg(
            name="mode",
            validator=lambda x: str(x).capitalize() in ["AUTO", "NORM", "SING"],
            default="AUTO",
        )
    ],
)

RigolDHO._register_query(
    "trigger_type",
    "TRIG:MODE",
    response_parser=None,
    args=[GenericDriver.Arg(name="type", validator=str)],
)

RigolDHO._register_query(
    "enable_roll",
    "TIM:ROLL",
    args=[
        GenericDriver.Arg(
            name="Toggle",
            validator=lambda x: 1 if x else 0,
        )
    ],
    response_parser=None,
)

RigolDHO._register_query(
    "set_timescale",
    "TIM:SCALE",
    response_parser=None,
    args=[
        GenericDriver.Arg(
            name="time",
            validator=lambda x: str(float(x)),
        )
    ],
)

RigolDHO._register_query(
    "set_data_source",
    "WAV:SOUR",
    args=[
        GenericDriver.Arg(
            name="source",
        )
    ],
    response_parser=None,
)

RigolDHO._register_query(
    "set_acquisition_depth",
    "ACQ:MDEP",
    args=[
        GenericDriver.Arg(
            name="memory",
        )
    ],
    response_parser=None,
)

RigolDHO._register_query(
    "set_horizontal_position",
    "TIM:HREF:POS",
    args=[
        GenericDriver.Arg(
            name="position",
            validator=lambda x: (int(x) if np.abs(x) <= 500 else 500 * np.sign(int(x))),
        )
    ],
    response_parser=None,
)


RigolDHO._register_query(
    "set_time_offset",
    "TIM:MAIN:OFFS",
    args=[GenericDriver.Arg(name="offset")],
    response_parser=str,
)

scope = RigolDHO(id="TCPIP::10.137.3.5::INSTR")
scope.reset()
