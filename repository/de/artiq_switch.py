import re

import numpy
from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import *
from regex import D

# This code outputs a single frequency at a fixed amplitude on a single channel of the urukul
# The following must be input from the dashboard:
# frequency(in MHz)
# amplitude(as amplitude scale factor so between 0 and 1)
#


class Urukul_Programmable(EnvExperiment):
    """Urukul Selectable Frequency, Amplitude, Attenuation and Pulse Length"""

    def build(self):  # This code runs on the host device

        self.setattr_device("core")
        used_uruk = []
        used_suservos = []
        for i in range(8):
            string_uruk = "urukul0_ch{it}".format(it=i)
            string_suservo = "suservo0_ch{it}".format(
                it=i
            )  ## We need a few devices, so this activates 4x urukuls and 8x suservo urukuls
            if i < 4:
                self.setattr_device(string_uruk)
                self.setattr_device(string_uruk)
                used_uruk.append(string_uruk)

            else:
                self.setattr_device(string_suservo)

            used_suservos.append(string_suservo)

        used_devices = [y for x in [used_uruk, used_suservos] for y in x]

        self.setattr_argument(
            "freq",
            NumberValue(
                default=0,
                unit="MHz",
                step=1,
                ndecimals=0,
            ),
        )  # instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument(
            "att", NumberValue(default=0, unit="dB", min=0, max=31.5, ndecimals=1)
        )  # instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument(
            "phase", NumberValue(default=0, min=0, max=1, ndecimals=2)
        )
        ## Option for phase TODO
        self.setattr_argument(
            "DDS", EnumerationValue(used_devices, default=used_devices[0])
        )

    # This code runs on the soft core processor within the FPGA
    def run(self):
        dds = self.get_device(self.DDS)

        dev_db = self.get_device_db()
        check_array = [d for d in dev_db.keys() if re.match(r"suservo\d+_ch\d+", d)]
        print(check_array)

        if self.get_device(self.DDS) in check_array:
            print("Yes it is")
        else:
            print("No it's not")
            # self.kernel_run(dds)

        # self.say_hello_from_core("2", dds)

    @kernel
    def kernel_run(self, dds):
        # type:(AD9912) -> None

        self.core.reset()  # resets core device
        dds.cpld.init()  # initialises CPLD on channel 1
        dds.init()

        att_reg = dds.cpld.get_att_mu()
        delay(250 * us)

        dds.set(self.freq, self.phase)
        dds.set_att(self.att)

        dds.sw.on()  # switches urukul channel on
        print("Done!")
