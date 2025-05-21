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

from repository.lib.fragments.read_adc import ReadSUServoADC


class TestPGIA(SetSUServoStatic):
    """
    Test the PGIA settings

    Set a static SUServo output and reads the ACD value
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "read_suservo_adc",
            ReadSUServoADC,
            self.get_device(self.channel),
        )
        self.read_suservo_adc: ReadSUServoADC

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

        self.setattr_result("adc_values", OpaqueChannel)
        self.adc_values: OpaqueChannel

        self.setattr_result("adc_mean", FloatChannel)
        self.adc_mean: FloatChannel

        self.setattr_result("adc_std_dev", FloatChannel)
        self.adc_std_dev: FloatChannel

    @kernel
    def run_once(self):

        values = [0.0] * self.number_of_points.get()

        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(),
            self.amplitude.get(),
            self.attenuation.get(),
            self.rf_switch.get(),
            self.setpoint_v.get(),
            self.enable_iir.get(),
        )

        self.LibSetSUServoStatic.set_pgia_gain_mu(self.pgia_setting.get())

        for i in range(self.number_of_points.get()):
            values[i] = self.read_suservo_adc.read_adc()
            delay(self.delay.get())

        sum = 0.0
        num = 0.0
        for i in range(1, len(values)):
            sum = sum + values[i]

        mean = sum / (len(values) - 1)
        for i in range(1, len(values)):
            num = num + (values[i] - mean) ** 2
        std_dev = (num / (len(values) - 1)) ** 0.5

        self.adc_values.push(values)
        self.adc_mean.push(mean)
        self.adc_std_dev.push(std_dev)

        self.set_dataset("adc_values", values, broadcast=True, archive=False)


TestPGIAExp = make_fragment_scan_exp(TestPGIA)
