from artiq.experiment import *
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import *
from RsInstrument import *

# See https://www.rohde-schwarz.com/webhelp/RTB_HTML_UserManual_en/Content/6f1f81df55074fde.htm
SETUP_CMDS = """
*RST
CHAN:TYPE HRES
CHAN:DATA:POIN DMAX
CHANnel1:SCALe 1e-3
CHANnel2:SCALe 10e-3
CHANnel1:COUPling ACLimit
CHANnel2:COUPling ACLimit
TIMebase:RANGe 0.000006
TRIGger:A:SOURce CH2
TRIGger:A:TYPE EDGE
TRIGger:A:LEVel1:VALue 0.0
WGENerator:FUNCtion SINusoid
WGENerator:VOLTage 0.1
WGENerator:VOLTage:OFFSet 0.0
WGENerator:FREQuency 500000
WGENerator:OUTPut ON
CHANnel1:STATe ON
CHANnel2:STATe ON
ACQuire:POINts 20000
"""


class ScanKoheronMeasureScopeFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

        self.laser_driver: CTL200 = self.get_device("blue_IJD1_controller")

    def host_setup(self):
        self.scope = RsInstrument("TCPIP::scope2.lan::INSTR", id_query=True, reset=True)

        for cmd in SETUP_CMDS.split("\n"):
            self.scope.write(cmd)

    def host_cleanup(self):
        self.scope.close()

    def run_once(self):
        # self.scope.write("CHANnel1:SCALe 1.0")
        pass


ScanKoheronMeasureScope = make_fragment_scan_exp(ScanKoheronMeasureScopeFrag)
