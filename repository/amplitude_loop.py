from artiq.experiment import *

#SUServo loop

class SuservoLoop(EnvExperiment):
    def build(self):
        self.setattr_device("core")  # Core device
        self.setattr_device("suservo0") 
        self.setattr_device("suservo0_ch0")  # Urukul channel to control amplitude
        
    @kernel #this code runs on the FPGA
    def run(self):
        self.core.reset()
        self.suservo0.init()
   
        self.suservo0.set_config(enable=1)
        
        # Set Sampler gain and Urukul attenuation
        g = 0
        a = 0.0
        self.suservo0.set_pgia_mu(0, g)         # set gain on Sampler channel 0 to 10^g
        self.suservo0.cpld0.set_att(0, A)       # set attenuation on Urukul channel 0 to 0
        
        
        # Set physical parameters
        v_t = 0.07                              # target input voltage (V) for Sampler channel - i have to define this based on experimentation 
        #i need to take measurements with the photodetector 
        f = 340000000                         # frequency (Hz) of Urukul output
        o = -v_t*(10.0**(g-1))                  # offset to assign to servo to reach target voltage

        # Set PI loop parameters 
        kp = 0                             # proportional gain
        ki = 0                             # integrator gainxb 
        gl = 0.0                           # integrator gain limit
        adc_ch = 0                         # Sampler channel to read from
        
        # Input parameters, activate Urukul output (en_out=1),
        # activate PI loop (en_iir=1)
        self.suservo0_ch0.set_iir(profile=0, adc=adc_ch, kp=kp, ki=ki, g=gl)
        self.suservo0_ch0.set_dds(profile=0, frequency=f, offset=o)
        self.suservo0_ch0.set(en_out=1, en_iir=1, profile=0)

























#############################################
        # Set Frequency & attenuation
        freq = 340e6
        attenuation = 0
        

        self.urukul0_ch0.set(freq)
        self.urukul0_ch0.set_att(attenuation)

        # self.urukul0_ch0.sw.on()  ????

        # Initial amplitude
        amplitude = 0
        self.urukul0_ch0.set(amplitude)

        # Final Amplitude and step size
        amplitude_final = 1
        step_size = 0.01

        sampler_output_list = []

        for i in range(amplitude, amplitude_final, step_size):
            #Set the new amplitude on the Urukul channel
            self.urukul0_ch0.set(amplitude = i)
            delay(2*us)

            #Get the feedback from the photodiode sampler
            sampler_output = self.sampler01.sample_mu(1) #what is the sampling rate? can it be 1?
            
            #Determine the max signal from the photodiode
            max_signal = max(sampler_output)
            
            sampler_output_list.append((amplitude, sampler_output))
                
        #set urukul to the amplitude corresponding to the max_signal

        self.urukul0_ch0.set(amplitude = max_signal)




