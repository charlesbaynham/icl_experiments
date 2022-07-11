import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.spi2 import SPIMaster
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import *


class OvenSpectroscopy(EnvExperiment):
    """Oven Spectroscopy control loop"""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("suservo0")
        self.setattr_device("suservo0_ch0")
        self.setattr_device("suservo0_ch1")
        self.setattr_device("fastino0")

        self.setattr_argument(
            "freq",
            NumberValue(
                default=0,
                unit="MHz",
                step=1,
                ndecimals=0,
            ),
        )  # instructs dashboard to take input in MHz and set it as an attribute called freq
        # self.setattr_argument("att", NumberValue(default = 0, unit = "dB", min = 0, max = 31.5, ndecimals = 1))                  #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument(
            "phase", NumberValue(default=0, min=0, max=1, ndecimals=2)
        )
        self.setattr_argument(
            "offset", NumberValue(default=0, unit="V", min=0, max=1.0, ndecimals=1)
        )
        self.setattr_argument(
            "samples", NumberValue(default=5000, step=5000, ndecimals=0)
        )
        self.setattr_argument("Delay", NumberValue(default=500, unit="us", ndecimals=0))
        self.setattr_argument("kp", NumberValue(default=-0.1, ndecimals=5))
        self.setattr_argument("ki", NumberValue(default=-300, ndecimals=5))
        # self.setattr_argument("runs", NumberValue(default = 1, min = 1, max = 5, ndecimals = 0))

    def run(self):
        n_steps = 100
        voltages = [(5 / n_steps) * i for i in range(n_steps + 1)]
        voltages = [
            y for x in [voltages, voltages[::-1]] for y in x
        ]  ## Builds an array of Voltages based on the number of input steps

        self.set_dataset(  ### Creates a dataset that will mutate elements to interpret and rework the output of the urukul
            "Photodetector_Data", np.full(self.samples, np.nan), broadcast=True
        )

        self.set_dataset(
            "Stabilisation_Data", np.full(self.samples, np.nan), broadcast=True
        )

        self.pass_Voltage(voltages)  ## Passes values into the function.

    @kernel
    def pass_Voltage(self, voltage):
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
        self.suservo0_ch0.set_y(profile=0, y=0.0)  # clear integrator

        self.suservo0_ch1.set_y(profile=0, y=0.0)  # clear integrator

        self.suservo0_ch0.set_iir(
            profile=0,
            adc=0,  # take data from Sampler channel 0
            kp=-0.1,  # -0.1 P gain
            ki=-300.0 / s,  # low integrator gain
            g=0.0,  # no integrator gain limit
            delay=0.0,  # no IIR update delay after enabling
        )

        self.suservo0_ch1.set_iir(
            profile=0,
            adc=1,  # take data from Sampler channel 1
            kp=self.kp,  # -0.1 P gain
            ki=self.ki / s,  # low integrator gain
            g=0.0,  # no integrator gain limit
            delay=0.0,  # no IIR update delay after enabling
        )

        self.suservo0_ch0.set_dds(
            profile=int(0),
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=self.freq,
            phase=self.phase,
        )

        self.suservo0_ch1.set_dds(
            profile=int(0),
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=self.freq,
            phase=self.phase,
        )

        # self.suservo0_ch0.set_iir(profile=0, adc=0, kp=1.0, ki=1.0)  ### PID stuff

        # enable RF, IIR updates and profile 0
        self.suservo0_ch0.set(en_out=1, en_iir=1, profile=0)
        self.suservo0_ch1.set(en_out=1, en_iir=1, profile=0)

        # enable global servo iterations
        self.suservo0.set_config(enable=1)

        self.core.break_realtime()
        self.fastino0.init()

        with parallel:
            for j in range(int(len(voltage))):

                for (
                    value
                ) in (
                    voltage
                ):  ## Outputting voltage to the fastino for 461 frequency modulation
                    self.fastino0.set_dac(0, value)
                    delay(50 * us)

            with sequential:
                for i in range(
                    int(self.samples)
                ):  ## Handling the data of the absorption photodetector
                    self.mutate_dataset(
                        "Photodetector_Data", i, self.suservo0.get_adc(0)
                    )

                    delay(self.Delay)

            with sequential:
                for i in range(
                    int(self.samples)
                ):  ## Handling the data of the stabilisation photodetector
                    self.mutate_dataset(
                        "Stabilisation_Data", i, self.suservo0.get_adc(1)
                    )

                    delay(self.Delay)
