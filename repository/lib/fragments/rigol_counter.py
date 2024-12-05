from ndscan.experiment import Fragment
import vxi11
import logging


logger = logging.getLogger(__name__)


class RigolCounterFrag(Fragment):
    def build_fragment(self, rigol_ip=None):
        self.rigol_ip = rigol_ip or "rigol-dg4162-b.lan"

    def host_setup(self):
        self.instr = self.get_interface_lan(self.rigol_ip)
        self.setup_measurement()

    def get_interface_lan(self, rigol_ip):
        instr = vxi11.Instrument(rigol_ip)

        class QueryAndWrite:
            def write(self, q):
                return instr.write(q)

            def query(self, q):
                return instr.ask(q)

        return QueryAndWrite()

    def get_frequency_str(self):
        query_result = self.instr.query(":COUN:MEAS?")
        frequency, *_ = query_result.split(",")
        return frequency

    def setup_measurement(self):
        """
        set gate time to 10 s and reset the counter
        """
        self.instr.write(":COUN:GATE USER5")  # 10 s gate time
        self.instr.write(":COUN:STAT OFF")  # reset the counter
        self.instr.write(":COUN:STAT ON")
