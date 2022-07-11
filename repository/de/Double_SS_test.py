import numpy as np
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import *


class SUServoTest(EnvExperiment):
    """Testing a Two Sampler Channels in Parallel"""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("suservo0")
        self.setattr_device("suservo0_ch0")
        self.setattr_device("suservo0_ch1")

        self.setattr_argument(
            "Frequency", NumberValue(default=0, unit="MHz", step=10, ndecimals=0)
        )
        self.setattr_argument(
            "Phase", NumberValue(default=0, min=0, max=1, ndecimals=1)
        )
        self.setattr_argument(
            "Offset", NumberValue(default=-0.5, unit="V", max=5, ndecimals=1)
        )
        self.setattr_argument(
            "Attenuation", NumberValue(default=10, unit="dB", ndecimals=0)  #
        )
        self.setattr_argument("n", NumberValue(default=5000, step=5000, ndecimals=0))

        self.setattr_argument(
            "Delay", NumberValue(default=5, unit="ms", min=0, ndecimals=4)
        )

        self.setattr_argument("kp", NumberValue(default=-0.1, ndecimals=5))

        self.setattr_argument("ki", NumberValue(default=-300.0, ndecimals=5))

    def run(self):
        self.set_dataset("Sampler_Data", np.full(int(self.n), np.nan), broadcast=True)
        self.set_dataset("Sampler2_Data", np.full(int(self.n), np.nan), broadcast=True)

        self.run_core()
        print("done!")

    @kernel
    def run_core(self):
        cpld = self.suservo0.cplds[0]
        self.core.reset()

        self.suservo0.init()
        delay(1 * us)

        for i in range(8):
            self.suservo0.set_pgia_mu(i, 0)
            delay(10 * us)

        cpld.set_att(0, self.Attenuation)
        delay(1 * us)

        assert self.suservo0.get_status() & 0xFF == 2

        delay(120 * us)

        self.suservo0_ch0.set_y(profile=0, y=0.0)
        self.suservo0_ch1.set_y(profile=0, y=0.0)

        self.suservo0_ch0.set_iir(
            profile=0, adc=0, kp=self.kp, ki=self.ki, g=0.0, delay=0.0
        )
        self.suservo0_ch1.set_iir(
            profile=0, adc=1, kp=self.kp, ki=self.ki, g=0.0, delay=0.0
        )

        self.suservo0_ch0.set_dds(
            profile=0, offset=self.Offset, frequency=self.Frequency, phase=self.Phase
        )
        self.suservo0_ch1.set_dds(
            profile=0, offset=self.Offset, frequency=self.Frequency, phase=self.Phase
        )

        self.suservo0_ch0.set(en_out=1, en_iir=1, profile=0)
        self.suservo0_ch1.set(en_out=1, en_iir=1, profile=0)

        self.suservo0.set_config(enable=1)

        self.core.break_realtime()

        # with parallel:
        for i in range(int(self.n)):
            sampler1 = self.suservo0.get_adc(0)
            delay(self.Delay / 4)
            self.mutate_dataset("Sampler_Data", i, sampler1)
            delay(self.Delay / 4)
            sampler2 = self.suservo0.get_adc(1)
            delay(self.Delay / 4)
            self.mutate_dataset("Sampler2_Data", i, sampler2)
            delay(self.Delay / 4)
            # for i in range(int(self.n)):
