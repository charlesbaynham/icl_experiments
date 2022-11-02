import re

import numpy
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD

from artiq.experiment import *
                     #imports everything from the artiq experiment library

#This code outputs a single frequency at a fixed amplitude on a single channel of the urukul
#The following must be input from the dashboard:
#frequency(in MHz)
#amplitude(as amplitude scale factor so between 0 and 1)
#attenuation(in db, between 0 and 31.5)
#pulse length(in s)

class Urukul_Programmable(EnvExperiment):
    """Urukul Test"""
    def build(self): #This code runs on the host device

        self.setattr_device("core")               #sets core device drivers as attributes
        self.setattr_device("suservo0")
        self.setattr_device("suservo0_ch0")

        self.setattr_device("suservo1")
        self.setattr_device("suservo1_ch0")


        self.suservo0 : SUServo
        self.suservo0_ch0 : Channel
        
        
    @kernel
    def run(self):
        
        cpld = self.suservo0.cplds[0]
        self.core.reset()


        self.suservo1.init()
        delay(1 * us)

        # ADC PGIA gain
        # for i in range(8):
        #     self.suservo0.set_pgia_mu(i, 0)
        #     delay(10 * us)

        # DDS attenuator
        cpld.set_att(0, 0.)
        delay(1 * us)



        # set up profile 0 on channel 0:
        delay(120 * us)
        self.suservo0_ch0.set_y(profile=0, y=1.0)  # clear integrator
        
        self.suservo0_ch0.set_dds(
            profile=0,
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=100e6,
            phase=0.0,
        )
        # enable RF, IIR updates and profile 0
        self.suservo0_ch0.set(en_out=1, en_iir=0, profile=0)
        # enable global servo iterations
        self.suservo0.set_config(enable=1)


    # def run(self): 
    #     dds = self.get_device(self.DDS)
    #     print(dds)
    #     self.fpga(dds)
        
    # @kernel
    # def fpga(self, dds):
    #     # type:(Channel) -> None

        
    #     self.core.reset()  # resets core device
        
    #     cpld = self.suservo0.cplds[0]
    #     self.core.reset()

    #     self.suservo0.init()
    #     delay(1 * us)

    #     # ADC PGIA gain
    #     for i in range(8):
    #         self.suservo0.set_pgia_mu(i, 0)
    #         delay(10 * us)

    #     # DDS attenuator
    #     cpld.set_att(0, 10.0)
    #     delay(1 * us)

    #     # Servo is done and disabled
    #     assert self.suservo0.get_status() & 0xFF == 2

    #     # set up profile 0 on channel 0:
    #     delay(120 * us)
    #     dds.set_y(profile=0, y=0.0)  # clear integrator
    #     dds.set_dds(
    #         profile=0,
    #         offset=-0.5,  # 5 V with above PGIA settings
    #         frequency=self.freq,
    #         phase=self.phase,
    #     )
    #     # enable RF, IIR updates and profile 0
    #     dds.set(en_out=1, en_iir=0, profile=0)
    #     # enable global servo iterations
    #     self.suservo0.set_config(enable=1)