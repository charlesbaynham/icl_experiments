from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.experiment import kernel
from ndscan.experiment import BoolParam
from ndscan.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.lib.utils import get_local_devices

from repository.lib.fragments.suservo import LibSetSUServoStatic


class SetSUServoStatic(ExpFragment):
    """
    Set a static SUServo output

    This ExpFragment just breaks out the functionality of
    :class:`.LibSetSUServoStatic`.
    """

    def build_fragment(self):
        self.setattr_device("core")

        self.setattr_param(
            "frequency",
            FloatParam,
            description="Static frequency of the SUServo channel",
            default=100e6,
            min=0,
            max=400e6,  # from AD9910 specs
            unit="MHz",
            step=1,
        )

        self.setattr_param(
            "amplitude",
            FloatParam,
            description="Amplitude of AD9910 output, from 0 to 1",
            default=1.0,
            min=0,
            max=1,
        )
        self.setattr_param(
            "attenuation",
            FloatParam,
            description="Attenuation on Urukul's variable attenuator",
            default=30,
            unit="dB",
            min=0,
            max=31.5,
        )
        self.setattr_param(
            "rf_switch",
            BoolParam,
            description="State of the RF switch",
            default=True,
        )

        self.amplitude: FloatParamHandle
        self.frequency: FloatParamHandle
        self.attenuation: FloatParamHandle
        self.rf_switch: BoolParamHandle

        suservo_channels = get_local_devices(self, SUServoChannel)
        if not suservo_channels:
            raise ValueError("No suservo channels found in device_db")
        self.setattr_argument("channel", EnumerationValue(suservo_channels))

        self.setattr_fragment("LibSetSUServoStatic", LibSetSUServoStatic, self.channel)
        self.LibSetSUServoStatic: LibSetSUServoStatic

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(),
            self.amplitude.get(),
            self.attenuation.get(),
            self.rf_switch.get(),
        )


SetSUServoStaticExp = make_fragment_scan_exp(SetSUServoStatic)
