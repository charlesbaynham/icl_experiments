import re

import numpy
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import *
from regex import D

# This code outputs a single frequency at a fixed amplitude on a single channel of the urukul
# The following must be input from the dashboard:
# frequency(in MHz)
# amplitude(as amplitude scale factor so between 0 and 1)
#


class SetUrukulChannel(EnvExperiment):
    """Set Urukul frequency, amplitude, attenuation and Pulse Length"""

    def build(self):  # This code runs on the host device

        self.setattr_device("core")
        self.setattr_device("suservo0")

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

        used_suservos.append("fastino0")
        self.setattr_device("fastino0")
        global used_devices
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
        check_2 = [d for d in dev_db.keys() if re.match(r"urukul\d+_ch\d+", d)]

        Dev_DDS = self.DDS
        Phase = self.phase
        Frequency = self.freq
        Attenuation = self.att

        if len([i for i, val in enumerate(check_array) if val == self.DDS]) > 0:
            print("SU Servo")
            self.kernel_run_S(dds)

        elif len([i for i, val in enumerate(check_2) if val == self.DDS]) > 0:
            print("Urukul")
            self.kernel_run_U(dds)

        else:
            print("Fastino")
            self.kernel_run_F(dds)

        print(
            "Done! Settings:\nDevice:{deedee}\nFrequency: {fr} /MHz\nAttenuation: {attn} /dB\nPhase: {ph} /scale".format(
                deedee=Dev_DDS, fr=Frequency / 10e5, attn=Attenuation, ph=Phase
            )
        )

    @kernel
    def kernel_run_U(self, dds):
        # type:(AD9912) -> None

        self.core.reset()  # resets core device

        dds.cpld.init()  # initialises CPLD on channel 1
        dds.init()

        att_reg = dds.cpld.get_att_mu()
        delay(250 * us)

        dds.set(self.freq, self.phase)
        dds.set_att(self.att)

        dds.sw.on()  # switches urukul channel on

    @kernel
    def kernel_run_S(self, dds):
        # type:(Channel) -> None

        cpld = self.suservo0.cplds[0]
        self.core.reset()

        self.suservo0.init()
        delay(1 * us)

        # ADC PGIA gain
        for i in range(8):
            self.suservo0.set_pgia_mu(i, 0)
            delay(10 * us)

        # DDS attenuator
        cpld.set_att(0, 10.0)
        delay(1 * us)

        # Servo is done and disabled
        assert self.suservo0.get_status() & 0xFF == 2

        # set up profile 0 on channel 0:
        delay(120 * us)
        dds.set_y(profile=0, y=0.0)  # clear integrator
        dds.set_iir(
            profile=0,
            adc=7,  # take data from Sampler channel 7
            kp=-0.1,  # -0.1 P gain
            ki=-300.0 / s,  # low integrator gain
            g=0.0,  # no integrator gain limit
            delay=0.0,  # no IIR update delay after enabling
        )
        # setpoint 0.5 (5 V with above PGIA gain setting)
        # 71 MHz
        # 0 phase
        dds.set_dds(
            profile=0,
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=self.freq,
            phase=self.phase,
        )
        # enable RF, IIR updates and profile 0
        dds.set(en_out=1, en_iir=1, profile=0)
        # enable global servo iterations
        self.suservo0.set_config(enable=1)
        # dds.set_dds(profile, frequency, offset, phase)

    @kernel
    def kernel_run_F(self, dds):
        # type:(Fastino) -> None
        print("yo")
        self.core.reset()
        # self.core.break_realtime()
        delay(250 * us)
        dds.init()
