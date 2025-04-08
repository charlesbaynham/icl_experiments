from artiq.coredevice.ad9910 import AD9910
from artiq.experiment import kernel
from pyaion.utilities.set_suservo_static import SetSUServoStatic
from pyaion.utilities.set_suservo_static import SetSUServoStaticExp  # noqa


class AmplitudeTest(SetSUServoStatic):
    """Print the amplitude tuning word"""

    @kernel
    def run_once(self):
        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(),
            self.amplitude.get(),
            self.attenuation.get(),
            self.rf_switch.get(),
            self.setpoint_v.get(),
            self.enable_iir.get(),
        )

        self.LibSetSUServoStatic.set_pgia_gain_mu(self.pgia_setting.get())

        channel = self.LibSetSUServoStatic.suservo_channel
        dds: AD9910 = self.LibSetSUServoStatic.suservo.ddses[channel[-1]]
        print(dds.get_asf())
