import re

import numpy
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.fastino import Fastino
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import *
from regex import D                                #imports everything from the artiq experiment library

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

        dev_db = self.get_device_db()
        check_array = [d for d in dev_db.keys() if re.match(r"suservo\d+_ch\d+", d)]
        
        for val in check_array:
            self.setattr_device(val)
                                                   #sets urukul0, channel 1 device drivers as attributes
        self.setattr_argument("freq", NumberValue(ndecimals=0, unit="MHz", step=1))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("amp", NumberValue(ndecimals=2, step=1))                  #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("atten", NumberValue(ndecimals=2, step=1))                #instructs dashboard to take input and set it as an attribute called atten
        self.setattr_argument("DDS", EnumerationValue(check_array, default=check_array[0]))
    

    @kernel #This code runs on the FPGA
    def run(self): 
        # type:(Channel) -> None
        dds = self.get_device(self.DDS)

        print(dds)
        self.core.reset()  # resets core device
        
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
        dds.set_dds(
            profile=0,
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=self.freq,
            phase=self.phase,
        )
        # enable RF, IIR updates and profile 0
        dds.set(en_out=1, en_iir=0, profile=0)
        # enable global servo iterations
        self.suservo0.set_config(enable=1)
       
        """
        dds.set_dds(
            profile=0,
            offset=-0.5,  # 5 V with above PGIA settings
            frequency=self.freq,
            phase=self.phase,
        )
        # enable RF, IIR updates and profile 0
        dds.set(en_out=1, en_iir=0, profile=0)
        # enable global servo iterations
        self.suservo0.set_config(enable=1)

        dds.cpld.init()  # initialises CPLD on channel 1
        dds.init()

        att_reg = dds.cpld.get_att_mu()
        delay(250 * us)

        dds.set(self.freq, self.phase)
        dds.set_att(self.att)

        dds.sw.on()  # switches urukul channel on                             #switches urukul channel off
        """