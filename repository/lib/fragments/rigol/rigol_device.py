from unittest.mock import MagicMock

import vxi11

GATE_TIMES_TO_IDX = {
    "1 ms": "1",
    "10 ms": "2",
    "100 ms": "3",
    "1 s": "4",
    "10 s": "5",
}


class RigolCounter:
    def __init__(self, device_mgr, rigol_ip=None, gate_time="10 s"):
        rigol_ip = rigol_ip or "rigol-dg4162-b.lan"
        self.gate_time_index = GATE_TIMES_TO_IDX[gate_time]
        self.instr = self.get_interface_lan(rigol_ip)

    def get_frequency_str(self):
        query_result = self.instr.query(":COUN:MEAS?")
        frequency, *_ = query_result.split(",")
        return frequency

    def get_frequency(self):
        """frequency in Hz as float"""
        return float(self.get_frequency_str())

    def setup_measurement(self):
        """
        set gate time and reset the counter
        """
        self.instr.write(":COUN:GATE USER" + self.gate_time_index)
        self.instr.write(":COUN:STAT OFF")  # reset the counter
        self.instr.write(":COUN:STAT ON")

    def get_interface_lan(self, rigol_ip):
        instr = vxi11.Instrument(rigol_ip)

        class QueryAndWrite:
            def write(self, q):
                return instr.write(q)

            def query(self, q):
                return instr.ask(q)

        return QueryAndWrite()


class MockRigolCounter(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.get_frequency = MagicMock()
        self.get_frequency.return_value = 80.0e6
