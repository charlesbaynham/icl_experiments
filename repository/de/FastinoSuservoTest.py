from artiq.experiment import*   
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.suservo import SUServo, Channel
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.spi2 import SPIMaster
import numpy as np; import matplotlib.pyplot as plt


class fastino_test(EnvExperiment):
    """Testing Fastino-SU Servo connection"""
    def build(self):
        self.setattr_device("core")
        self.setattr_device("suservo0"); self.setattr_device("suservo0_ch0")
        self.setattr_device("fastino0")

        self.setattr_argument("freq", NumberValue(default = 0, unit = "MHz", step = 1, ndecimals = 0,))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("att", NumberValue(default = 0, unit = "dB", min = 0, max = 31.5, ndecimals = 1))                  #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("phase", NumberValue(default = 0, min = 0, max = 1, ndecimals = 2))
        self.setattr_argument("offset", NumberValue(default = 0, unit = "V", min = 0, max = 1., ndecimals = 1))
        self.setattr_argument("runs", NumberValue(default = 1, min = 1, max = 5, ndecimals = 0))

    def run(self):
        n_steps = 100
        voltages = [(5/n_steps) * i 
            for i in range(n_steps + 1)]
        voltages = [y for x in [voltages, voltages[::-1]] for y in x]
        empty = np.zeros(len(voltages) * int(self.runs))

        sampler_values = self.pass_Voltage(voltages, empty, int(self.runs))
        print(sampler_values)
        plt.plot(sampler_values)


    @kernel
    def pass_Voltage(self, voltage, empty, n):
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
        
        self.core.break_realtime()
        self.fastino0.init()

        #i = 0
        for j in range(n):
            for value in voltage:
                #
                self.fastino0.set_dac(0, value)
            #self.fastino0.load()
                empty[voltage.index(value) + (1 * j)] = self.suservo0.get_adc(0)
                self.core.break_realtime()
                delay(7 * ns)
            
        return empty
            
            #self.core.break_realtime()
