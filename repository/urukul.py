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
        #self.setattr_device("urukul2_ch1")
         
        urukuls = []
        for i in range(4):
            string = "urukul2_ch{a}".format(a = i)
            self.setattr_device(string)
            urukuls.append(string)
            
            #self.urukul2_ch1 = self.get_device("urukul2_ch0")
        
       
        self.setattr_argument("freq", NumberValue(ndecimals=0, unit="MHz", step=1, min=0))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("amp", NumberValue(ndecimals=2, step=0.5, min = 0, max = 1))     #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("atten", NumberValue(ndecimals=2, unit="dB", step=0.1, min=0))                                        #instructs dashboard to take input and set it as an attribute called atten
        self.setattr_argument("urukul_channel", EnumerationValue(urukuls, default = urukuls[0]))
        
        #self.my_urukul : AD9910 = self.get_device(self.urukul_channel)
        self.my_urukul = self.get_device(self.urukul_channel)
        
    
    @kernel 
    def run(self):  

        self.core.reset()          
        my_urukul = self.my_urukul                            
        my_urukul.cpld.init()                            
        my_urukul.init()                                                                        
        
        
        my_urukul.set_att(self.atten)                    #writes attenuation to urukul channel
        my_urukul.sw.on()                                #switches urukul channel on
           
            
        my_urukul.set(self.freq, amplitude = self.amp)   #writes frequency and amplitude attributes to urukul channel thus outputting function                             #delay determined by user input
                                