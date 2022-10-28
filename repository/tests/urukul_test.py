import artiq
                               

from artiq.experiment import*                                   #imports everything from the artiq experiment library

#This code outputs a single frequency at a fixed amplitude on a single channel of the urukul
#The following must be input from the dashboard:
#frequency(in MHz)
#amplitude(as amplitude scale factor so between 0 and 1)
#attenuation(in db, between 0 and 31.5)
#pulse length(in s)

class Urukul_Programmable(EnvExperiment):
    """Urukul Test"""
    def build(self): #This code runs on the host device
        

        self.setattr_device("core")                                                     #sets core device drivers as attributes
        self.setattr_device("suservo0")   
        
        check_array = [d for d in dev_db.keys() if re.match(r"suservo\d+_ch\d+", d)]
        check_2 = [d for d in dev_db.keys() if re.match(r"urukul\d+_ch\d+", d)]
                                                   #sets urukul0, channel 1 device drivers as attributes
        self.setattr_argument("freq", NumberValue(ndecimals=0, unit="MHz", step=1))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("amp", NumberValue(ndecimals=2, step=1))                  #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("atten", NumberValue(ndecimals=2, step=1))                #instructs dashboard to take input and set it as an attribute called atten
        self.setattr_argument("t_pulse", NumberValue(ndecimals=2, unit = "s", step=1))  #instructs dashboard to take input and set it as an attribute called t_pulse
        
    
    @kernel #This code runs on the FPGA
    def run(self):  
        self.core.reset()                                       #resets core device
        self.suservo0.cpld.init()                            #initialises CPLD on channel 1
        self.suservo0.init()                                 #initialises channel 1
        delay(10 * ms)                                          #10ms delay
        
        
        self.suservo0.set_att(self.atten)                    #writes attenuation to urukul channel
        self.suservo0.sw.on()                                #switches urukul channel on
           
            
        self.suservo0.set(self.freq, amplitude = self.amp)   #writes frequency and amplitude attributes to urukul channel thus outputting function
        delay(self.t_pulse * s)                                 #delay determined by user input
        self.suservo0.sw.off()                               #switches urukul channel off