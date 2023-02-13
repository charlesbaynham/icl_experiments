from artiq.coredevice.core import Core
from artiq.coredevice.suservo import SUServo
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment


class ReadSUServoADC(ExpFragment):
    """
    Reads the voltage on a SUServo input channel

    The device and channel to be read are passed as arguments to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "ReadSUServoADC", ReadSUServoADC, "suservo0", 2,
        )
    """

    def build_fragment(self, suservo_device: str, suservo_channel: int):
        self.suservo_channel: int = suservo_channel
        self.suservo_device: str = suservo_device

    def host_setup(self):
        super().host_setup()
        self.core: Core = self.get_device("core")
        self.suservo: SUServo = self.get_device(self.suservo_device)

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.suservo.init()
        self.suservo.set_config(enable=1)

    @kernel
    def read_adc(self):
        return self.suservo.get_adc(self.suservo_channel)
