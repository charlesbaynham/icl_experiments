from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue
from artiq.experiment import TFloat
from artiq.experiment import TInt32


class SetSUServoStatic(EnvExperiment):
    """Set a static SUServo output

    This Experiment will reinitialise the SUServo, clearing any currently set frequencies
    """

    def build(self):
        self.setattr_device("core")

        # used_uruk = []
        # used_suservos = []

        # for i in range(8):
        #     string_uruk = "urukul0_ch{it}".format(it=i)
        #     string_suservo = "suservo0_ch{it}".format(
        #         it=i
        #     )  ## We need a few devices, so this activates 4x urukuls and 8x suservo urukuls
        #     if i < 4:
        #         self.setattr_device(string_uruk)
        #         used_uruk.append(string_uruk)

        #     else:
        #         self.setattr_device(string_suservo)

        #     used_suservos.append(string_suservo)

        # used_suservos.append("fastino0")
        # self.setattr_device("fastino0")
        # global used_devices
        # used_devices = [y for x in [used_uruk, used_suservos] for y in x]

        # self.setattr_argument(
        #     "freq",
        #     NumberValue(
        #         default=0,
        #         unit="MHz",
        #         step=1,
        #         ndecimals=0,
        #     ),
        # )  # instructs dashboard to take input in MHz and set it as an attribute called freq
        # self.setattr_argument(
        #     "att", NumberValue(default=0, unit="dB", min=0, max=31.5, ndecimals=1)
        # )  # instructs dashboard to take input and set it as an attribute called amp
        # self.setattr_argument(
        #     "phase", NumberValue(default=0, min=0, max=1, ndecimals=2)
        # )

        # ## Option for phase TODO
        # self.setattr_argument(
        #     "DDS", EnumerationValue(used_devices, default=used_devices[0])
        # )

    def run(self):
        chan = self.get_device("suservo0_ch0")
        self.init_and_set_suservo(chan, 200.0e6, 0.5)

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
