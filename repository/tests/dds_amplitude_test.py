from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import IntParam
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParamHandle
from pyaion.utilities.set_suservo_static import SetSUServoStatic


class AmplitudeTest(SetSUServoStatic):
    """
    Record the amplitude scale factor

    Set a static suservo output and record the amplitude scale factor
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay",
            FloatParam,
            description="delay between points",
            default=0.0001,
        )
        self.delay: FloatParamHandle

        self.setattr_param(
            "number_of_points",
            IntParam,
            description="number of points",
            default=50,
        )
        self.number_of_points: IntParamHandle

        self.setattr_result("asf_values", OpaqueChannel)
        self.asf_values: OpaqueChannel

        self.setattr_result("asf_mean", FloatChannel)
        self.asf_mean: FloatChannel

        self.setattr_result("asf_std_dev", FloatChannel)
        self.asf_std_dev: FloatChannel

    @kernel
    def run_once(self):
        amplitude_mu = [0] * self.number_of_points.get()

        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(),
            self.amplitude.get(),
            self.attenuation.get(),
            self.rf_switch.get(),
            self.setpoint_v.get(),
            self.enable_iir.get(),
        )

        self.LibSetSUServoStatic.set_pgia_gain_mu(self.pgia_setting.get())

        delay(2.0e-1)
        dds = self.LibSetSUServoStatic.suservo.ddses[0]

        for i in range(self.number_of_points.get()):
            amplitude = self.LibSetSUServoStatic.suservo_channel.get_y(2)
            amplitude_mu[i] = dds.amplitude_to_asf(amplitude)
            delay(self.delay.get())

        sum = 0.0
        num = 0.0
        for i in range(1, len(amplitude_mu)):
            sum = sum + amplitude_mu[i]

        mean = sum / (len(amplitude_mu) - 1)
        for i in range(1, len(amplitude_mu)):
            num = num + (amplitude_mu[i] - mean) ** 2
        std_dev = (num / (len(amplitude_mu) - 1)) ** 0.5

        self.asf_values.push(amplitude_mu)
        self.asf_mean.push(mean)
        self.asf_std_dev.push(std_dev)

        self.set_dataset("asf_values", amplitude_mu, broadcast=True, archive=False)


AmplitudeTestExp = make_fragment_scan_exp(AmplitudeTest)
