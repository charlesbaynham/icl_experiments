from artiq.experiment import *

#SUServo loop
#Change amplitude on urukul 
#Get feedback from photodiode sampler
#Determine max signal from photodiode and set corresponding urukul amplitude

class SuservoLoop(EnvExperiment):
    def build(self):
        self.setattr_device("core")  # Core device
        self.setattr_device("suservo1_0")  # Urukul channel to control amplitude
        #self.setattr_device("sampler0")

    @kernel #this code runs on the FPGA
    def run(self):
        self.core.reset()
        self.suservo1_ch01.init()
       

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




