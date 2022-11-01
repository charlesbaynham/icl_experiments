import re

from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue
from artiq.experiment import TFloat


class SetSUServoStatic(EnvExperiment):
    """Set a static SUServo output

    This Experiment will reinitialise the SUServo, clearing any currently set frequencies
    """

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "frequency",
            NumberValue(
                default=100e6,
                unit="MHz",
                step=1,
                ndecimals=2,
            ),
        )
        self.setattr_argument(
            "amplitude", NumberValue(default=1.0, min=0, max=1, ndecimals=1)
        )
        self.setattr_argument(
            "attenuation",
            NumberValue(default=30, unit="dB", min=0, max=31.5, ndecimals=1),
        )

        suservo_channels = [
            d for d in self.get_device_db().keys() if re.match(r"suservo\d+_ch\d+", d)
        ]
        self.setattr_argument(
            "channel", EnumerationValue(suservo_channels, default=suservo_channels[0])
        )

    def run(self):
        chan = self.get_device(self.channel)
        self.init_and_set_suservo(
            chan, self.frequency, self.amplitude, self.attenuation
        )

    @kernel
    def init_and_set_suservo(
        self,
        suservo_channel,
        freq: TFloat,
        amplitude: TFloat,
        attenuation: TFloat = 30.0,
    ):
        # type:(Channel, float, float, float) -> None

        suservo = suservo_channel.servo  # type: SUServo

        self.core.reset()
        delay(1 * ms)

        suservo.init()

        # Set the attenuator for this channel
        suservo_channel.dds.cpld.set_att(0, attenuation)

        # Configure profile 0 to have the requested amplitude and frequency
        suservo_channel.set_y(profile=0, y=amplitude)
        suservo_channel.set_dds(
            profile=0,
            offset=-0.5,  # Not used
            frequency=freq,
            phase=0.0,
        )

        # Enable profile 0 and the suservo more widely
        suservo_channel.set(en_out=1, en_iir=0, profile=0)
        suservo.set_config(enable=1)
