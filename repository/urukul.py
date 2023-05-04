from artiq.experiment import*                                
from artiq.coredevice.ad9910 import AD9910
class Urukul_Programmable(EnvExperiment):
    """Urukul frequency, amplitude and attenuation"""
    def build(self): 
        
        #urukuls = []
        #for i in range(4):
        #   urukuls.append("urukul0_ch{a}".format(a = i))

        self.setattr_device("core") 
        #sets core device drivers as attributes
        self.setattr_device("urukul2_ch1")
         
        # urukuls = []
        # for i in range(4):
        #     string = "urukul2_ch{a}".format(a = i)
        #     self.setattr_device(string)
        #     self.urukul0_ch1 = self.get_device("urukul0_ch0")
        
       
        self.setattr_argument("freq", NumberValue(ndecimals=0, unit="MHz", step=1, min=0))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("amp", NumberValue(ndecimals=2, step=0.5, min = 0, max = 1))     #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("atten", NumberValue(ndecimals=2, unit="dB", step=0.1, min=0))                                        #instructs dashboard to take input and set it as an attribute called atten
        #self.setattr_argument("urukul_channel", EnumerationValue(urukuls, default = urukuls[0]))
        
        #self.my_urukul : AD9910 = self.get_device(self.urukul_channel)

        
    
    @kernel 
    def run(self):  
        self.core.reset()                                      
        self.urukul2_ch1.cpld.init()                            
        self.urukul2_ch1.init()                                                                        
        
        
        self.urukul2_ch1.set_att(self.atten)                    #writes attenuation to urukul channel
        self.urukul2_ch1.sw.on()                                #switches urukul channel on
           
            
        self.urukul2_ch1.set(self.freq, amplitude = self.amp)   #writes frequency and amplitude attributes to urukul channel thus outputting function                             #delay determined by user input
                                