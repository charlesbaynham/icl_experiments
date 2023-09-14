from artiq.coredevice.ad9910 import AD9910
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel


class TurnOn689And10MHzRef(EnvExperiment):
    def build(self):
        self.setattr_device("core")

        self.setattr_device("urukul9910_aom_doublepass_689_red_injection")
        self.setattr_device("urukul8_ch3")

        self.urukul9910_aom_doublepass_689_red_injection: AD9910
        self.urukul8_ch3: AD9910

    @kernel
    def run(self):
        self.core.break_realtime()

        self.urukul8_ch3.init()
        self.urukul9910_aom_doublepass_689_red_injection.init()

        self.urukul9910_aom_doublepass_689_red_injection.set(
            frequency=340e6, amplitude=1.0
        )
        self.urukul8_ch3.set(frequency=10e6, amplitude=1.0)

        self.urukul9910_aom_doublepass_689_red_injection.set_att(0.0)
        self.urukul8_ch3.set_att(0.0)

        self.urukul9910_aom_doublepass_689_red_injection.sw.on()
        self.urukul8_ch3.sw.on()
