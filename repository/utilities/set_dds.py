from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.urukul import CPLD
from artiq.experiment import BooleanValue
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import kernel
from pyaion.lib.utils import get_local_devices


class SetDDS(EnvExperiment):
    """
    Basic DDS setter for AD9910s or AD9912s
    """

    def build(self):
        list_of_channels = get_local_devices(self, AD9910) + get_local_devices(
            self, AD9912
        )
        self.setattr_argument(
            "device_name",
            EnumerationValue(list_of_channels, default=list_of_channels[0]),
        )

        self.setattr_argument("frequency", NumberValue(default=100e6, unit="MHz"))
        self.setattr_argument(
            "attenuation", NumberValue(default=30, unit="dB", min=0, max=30)
        )
        self.setattr_argument("switch", BooleanValue(default=True))

        self.channel: AD9912 = self.get_device(self.device_name)
        self.setattr_device("core")

    def prepare(self):
        self.cpld: CPLD = self.channel.cpld

    @kernel
    def run(self):
        self.core.break_realtime()

        self.cpld.init()
        self.channel.init()

        # Load the attenuator settings for all channels
        self.cpld.get_att_mu()

        self.core.break_realtime()

        self.channel.sw.set_o(self.switch)
        self.channel.set(self.frequency)
        self.channel.set_att(self.attenuation)
