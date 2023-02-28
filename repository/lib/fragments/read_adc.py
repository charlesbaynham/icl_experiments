from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import SUServo
from artiq.experiment import kernel
from ndscan.experiment import Fragment


class ReadADC(Fragment):
    """
    Interface to read a voltage from an ARTIQ ADC

    This is an interface - you cannot use it directly and must use concrete
    implementations instead. This class defines a simple interface for taking a
    single reading from an ADC, abstracting away the details. Currently, the
    only possible ADC types are Samplers and SUServos - see
    :class:`~.ReadSamplerADC` and :class:`~.ReadSUServoADC`.
    """

    def build_fragment(self, *args, **kwargs):
        raise NotImplementedError

    def read_adc(self) -> float:
        raise NotImplementedError


class ReadSamplerADC(ReadADC):
    """
    Reads the voltage on a Sampler input channel

    The device and channel to be read are passed as arguments to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "ReadSamplerADC", ReadSamplerADC, "sampler0", 2,
        )
    """

    def build_fragment(self, sampler_device: Sampler, sampler_channel: int):
        self.sampler_channel: int = sampler_channel
        self.sampler_device: Sampler = sampler_device

    def host_setup(self):
        super().host_setup()
        self.core: Core = self.get_device("core")

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.sampler.init()

    @kernel
    def read_adc(self):
        samples = [0.0] * 8
        self.sampler.sample(samples)

        return samples[self.sampler_channel]


class ReadSUServoADC(ReadADC):
    """
    Reads the voltage on a SUServo input channel

    The device and channel to be read are passed as arguments to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "ReadSUServoADC", ReadSUServoADC, "suservo0", 2,
        )
    """

    def build_fragment(self, suservo_device: SUServo, suservo_channel: int):
        self.suservo_channel: int = suservo_channel
        self.suservo_device: SUServo = suservo_device

    def host_setup(self):
        super().host_setup()
        self.core: Core = self.get_device("core")

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.suservo.init()
        self.suservo.set_config(enable=1)

    @kernel
    def read_adc(self):
        return self.suservo.get_adc(self.suservo_channel)
