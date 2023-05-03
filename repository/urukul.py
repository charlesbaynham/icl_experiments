from artiq.experiment import*                                

class Urukul_Programmable(EnvExperiment):
    """Urukul frequency, amplitude and attenuation"""
    def build(self): 
        

        self.setattr_device("core")                                                     #sets core device drivers as attributes
        self.setattr_device("urukul0_ch1")                                              #sets urukul0, channel 1 device drivers as attributes
        self.setattr_argument("freq", NumberValue(ndecimals=0, unit="MHz", step=1))     #instructs dashboard to take input in MHz and set it as an attribute called freq
        self.setattr_argument("amp", NumberValue(ndecimals=2, step=1))                  #instructs dashboard to take input and set it as an attribute called amp
        self.setattr_argument("atten", NumberValue(ndecimals=2, step=1))                #instructs dashboard to take input and set it as an attribute called atten
        
        
    
    @kernel 
    def run(self):  
        self.core.reset()                                       #resets core device
        self.urukul0_ch1.cpld.init()                            #initialises CPLD on channel 1
        self.urukul0_ch1.init()                                 #initialises channel 1
        delay(10 * ms)                                          #10ms delay
        
        
        self.urukul0_ch1.set_att(self.atten)                    #writes attenuation to urukul channel
        self.urukul0_ch1.sw.on()                                #switches urukul channel on
           
            
        self.urukul0_ch1.set(self.freq, amplitude = self.amp)   #writes frequency and amplitude attributes to urukul channel thus outputting function                             #delay determined by user input
        self.urukul0_ch1.sw.off()                               #switches urukul channel off