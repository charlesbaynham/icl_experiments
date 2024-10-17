import time

import numpy as np
from artiq.experiment import *
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
from RsInstrument import *

# See https://www.rohde-schwarz.com/webhelp/RTB_HTML_UserManual_en/Content/6f1f81df55074fde.htm
SETUP_CMDS = """
*RST
CHAN:TYPE HRES
CHAN:DATA:POIN DMAX
CHANnel1:SCALe 1e-3
CHANnel1:COUPling ACLimit
CHANnel1:BANDwidth B20
CHANnel2:COUPling ACLimit
TRIGger:A:SOURce CH2
TRIGger:A:TYPE EDGE
TRIGger:A:LEVel1:VALue 0.0
WGENerator:FUNCtion SINusoid
WGENerator:VOLTage:OFFSet 0.0
WGENerator:FREQuency 500000
WGENerator:OUTPut ON
CHANnel1:STATe ON
CHANnel2:STATe ON
ACQuire:POINts 100000
"""


class ScanKoheronMeasureScope(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

        self.setattr_param(
            "timebase",
            FloatParam,
            description="Scope timebase",
            default=6e-6,
            unit="us",
            min=0,
        )
        self.timebase: FloatParamHandle

        self.setattr_param(
            "current",
            FloatParam,
            description="IJD1 current",
            default=0.350,
            unit="mA",
            max=0.38,
            min=0,
        )
        self.current: FloatParamHandle

        self.setattr_param(
            "amplitude",
            FloatParam,
            description="Modulation amplitude",
            default=0.025,
            unit="mV",
            max=1,
            min=0,
        )
        self.amplitude: FloatParamHandle

        self.laser_driver: CTL200 = self.get_device("blue_IJD1_controller")

        self.setattr_result("time", OpaqueChannel)
        self.setattr_result("current_modulation", OpaqueChannel)
        self.setattr_result("photodiode_signal", OpaqueChannel)

        self.time: ResultChannel
        self.current_modulation: ResultChannel
        self.photodiode_signal: ResultChannel

    def host_setup(self):
        self.scope = RsInstrument("TCPIP::scope2.lan::INSTR", id_query=True, reset=True)

        for cmd in SETUP_CMDS.split("\n"):
            self.scope.write(cmd)

    def host_cleanup(self):
        self.scope.write(f"WGENerator:OUTPut OFF")

        self.scope.close()

    def take_data(self):
        self.scope.write("SING")
        self.scope.query("*OPC?")

    def readout_data(self, chan):
        data_raw = self.scope.query_bin_or_ascii_float_list(
            "FORM ASC;:CHAN{}:DATA?".format(chan)
        )
        header = self.scope.query_bin_or_ascii_float_list(
            "CHANnel{}:DATA:HEADer?".format(chan)
        )

        x_vals = np.linspace(header[0], header[1], int(header[2])).tolist()

        return x_vals, data_raw

    def run_once(self):
        self.scope.write(f"WGENerator:VOLTage {self.amplitude.get()}")
        self.scope.write(f"TIMebase:RANGe {self.timebase.get()}")
        self.scope.write(f"CHANnel2:RANGe {3*self.amplitude.get()}")

        self.scope.query("*OPC?")

        self.laser_driver.set_current_mA(1e3 * self.current.get())

        time.sleep(0.5)

        self.take_data()

        t, data_ch1 = self.readout_data("1")
        t, data_ch2 = self.readout_data("2")

        self.time.push(t)
        self.photodiode_signal.push(data_ch1)
        self.current_modulation.push(data_ch2)


# HACK remove expfragment from namespace to get around unit testing accessing the scope
ScanKoheronMeasureScope = make_fragment_scan_exp(ScanKoheronMeasureScope)
