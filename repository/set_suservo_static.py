import re

from artiq.experiment import kernel
from artiq.experiment import StringValue
from ndscan.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.suservo import LibSetSUServoStatic


class SetSUServoStatic(ExpFragment):
    """
    Set a static SUServo output

    This ExpFragment just breaks out the functionality of
    :class:`.LibSetSUServoStatic`.
    """

    def build_fragment(self):
        self.setattr_param(
            "frequency",
            FloatParam,
            description="Static frequency of the SUServo channel",
            default=100e6,
            min=0,
            max=400e6,  # from AD9910 specs
            unit="MHz",
            step=1,
            # ndecimals=2,
        )

        self.setattr_param(
            "amplitude",
            FloatParam,
            description="Amplitude of AD9910 output, from 0 to 1",
            default=1.0,
            min=0,
            max=1,
            # ndecimals=1,
        )
        self.setattr_param(
            "attenuation",
            FloatParam,
            description="Attenuation on Urukul's variable attenuator",
            default=30,
            unit="dB",
            min=0,
            max=31.5,
            # ndecimals=1,
        )

        suservo_channels = [
            d for d in self.get_device_db().keys() if re.match(r"suservo\d+_ch\d+", d)
        ]
        self.setattr_argument("channel", EnumerationValue(suservo_channels))

        self.setattr_fragment("LibSetSUServoStatic", LibSetSUServoStatic, self.channel)
        self.LibSetSUServoStatic: LibSetSUServoStatic

    @kernel
    def run_once(self):
        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(), self.amplitude.get(), self.attenuation.get()
        )


SetSUServoStaticExp = make_fragment_scan_exp(SetSUServoStatic)
