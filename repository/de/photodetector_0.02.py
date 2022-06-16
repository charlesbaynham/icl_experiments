from artiq.experiment import*  
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.suservo import SUServo, Channel
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.spi2 import SPIMaster
import numpy as np; import matplotlib.pyplot as plt


class Photodetector(EnvExperiment):
    """Creating datasets from photodetector data"""
    def build(self):
        self.setattr_device("core")
        self.setattr_device("suservo0")
        self.setattr_device("suservo0_ch0")

        self.setattr_argument("freq", NumberValue(default = 0, unit = "MHz", step = 10, ndecimals = 0))
        self.setattr_argument("phase", NumberValue(default = 0, min = 0, max = 1, ndecimals = 1))
    
    
    def run(self):
        self.set_dataset(
            "Photodetector_Data",
            np.full(5000, np.nan, broadcast = True)
        )
        self.core_run()

    @kernel
    def core_run(self):    
        cpld = self.suservo0.cplds[0]
        self.core.reset()

        self.suservo0.init()
        delay(1*us)
       
        # ADC PGIA gain
        for i in range(8):
            self.suservo0.set_pgia_mu(i, 0)
            delay(10*us)
       
        # DDS attenuator
        cpld.set_att(0, 10.)
        delay(1*us)
       
        # Servo is done and disabled
        assert self.suservo0.get_status() & 0xff == 2

        # set up profile 0 on channel 0:
        delay(120*us)
        self.suservo0_ch0.set_y(
            profile=0,
            y=0.  # clear integrator
        )
        self.suservo0_ch0.set_iir(profile=0,
            adc=0,  # take data from Sampler channel 0
            kp=-.1,  # -0.1 P gain
            ki=-300./s,  # low integrator gain
            g=0.,  # no integrator gain limit
            delay=0.  # no IIR update delay after enabling
        )
        self.suservo0_ch0.set_dds(profile = int(0),
            offset = -.5,  # 5 V with above PGIA settings
            frequency = self.freq,
            phase = self.phase)
        # enable RF, IIR updates and profile 0
        self.suservo0_ch0.set(en_out=0, en_iir=1, profile=0)
        # enable global servo iterations
        self.suservo0.set_config(enable=1)

        for i in range(5000):
            self.mutate_dataset("Photodetector_Data", self.suservo0_ch0.get_adc(0), i)
            delay(50 * us)

