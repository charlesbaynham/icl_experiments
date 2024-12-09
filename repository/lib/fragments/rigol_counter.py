from ndscan.experiment import Fragment, FloatChannel
import logging
import vxi11
from artiq.language import host_only, rpc
from repository.lib.constants import CLOCK_LASER_BEATNOTE_FREQUENCY


logger = logging.getLogger(__name__)

GATE_TIMES_TO_IDX = {
    "1 ms": "1",
    "10 ms": "2",
    "100 ms": "3",
    "1 s": "4",
    "10 s": "5",
}


class RigolCounterFrag(Fragment):
    def build_fragment(self, rigol_ip=None):
        self.rigol_ip = rigol_ip or "rigol-dg4162-b.lan"
        self.gate_time_index = "10 s"
        self.setattr_result(
            "rigol_counter_frequency", FloatChannel, display_hints={"priority": -1}
        )
        self.rigol_counter_frequency: FloatChannel

    def host_setup(self):
        self.instr = self.get_interface_lan(self.rigol_ip)
        self.setup_measurement()
        super().host_setup()

    @host_only
    def get_interface_lan(self, rigol_ip):
        instr = vxi11.Instrument(rigol_ip)

        class QueryAndWrite:
            def write(self, q):
                return instr.write(q)

            def query(self, q):
                return instr.ask(q)

        return QueryAndWrite()

    @host_only
    def get_frequency_str(self):
        query_result = self.instr.query(":COUN:MEAS?")
        frequency, *_ = query_result.split(",")
        return frequency

    @host_only
    def get_frequency(self):
        """frequency in Hz as float"""
        return float(self.get_frequency_str())

    @host_only
    def setup_measurement(self):
        """
        set gate time and reset the counter
        """
        self.instr.write(
            ":COUN:GATE USER" + GATE_TIMES_TO_IDX[self.gate_time_index]
        )  # 10 s gate time
        self.instr.write(":COUN:STAT OFF")  # reset the counter
        self.instr.write(":COUN:STAT ON")

    @rpc
    def check_counter_rpc(self):
        frequency = self.rigol.get_frequency()
        if abs(frequency - CLOCK_LASER_BEATNOTE_FREQUENCY) > 200e-3:
            logger.warning(
                "Frequency %.2f is too far from expected %.2f",
                frequency,
                CLOCK_LASER_BEATNOTE_FREQUENCY,
            )

        self.rigol_counter_frequency.push(CLOCK_LASER_BEATNOTE_FREQUENCY - frequency)
