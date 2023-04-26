from typing import Optional

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
        pass

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

    def build_fragment(
        self,
        sampler_device: Optional[Sampler] = None,
        sampler_channel: Optional[int] = None,
    ):
        """
        Set up this Fragment

        If sampler_device and sampler_channel are not provided now they must be
        provided later before this Fragment is setup via :meth:`.set_settings`
        """
        self.sampler_channel = sampler_channel
        self.sampler_device = sampler_device

    def set_settings(self, sampler_device: Sampler, sampler_channel: int):
        self.sampler_device = sampler_device
        self.sampler_channel = sampler_channel

    def host_setup(self):
        if self.sampler_device is None or self.sampler_channel is None:
            raise ValueError(
                "sampler_device or sampler_channel is None. You must either pass these to build_fragment()"
                " or call set_settings() before Fragment setup"
            )

        super().host_setup()
        self.core: Core = self.get_device("core")

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.sampler_device.init()

    @kernel
    def read_adc(self):
        samples = [0.0] * 8
        self.sampler_device.sample(samples)

        return samples[self.sampler_channel]


class ReadSUServoADC(ReadADC):
    """
    Reads the voltage on a SUServo input channel

    The device and channel to be read are passed as arguments to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "ReadSUServoADC", ReadSUServoADC, "suservo0", 2,
        )
    """

    def build_fragment(
        self,
        suservo_device: Optional[SUServo] = None,
        suservo_channel: Optional[int] = None,
    ):
        """
        Set up this Fragment

        If suservo_device and suservo_channel are not provided now they must be
        provided later before this Fragment is setup via :meth:`.set_settings`
        """
        self.suservo_channel = suservo_channel
        self.suservo_device = suservo_device

    def set_settings(self, suservo_device: SUServo, suservo_channel: int):
        self.suservo_device = suservo_device
        self.suservo_channel = suservo_channel

    def host_setup(self):
        if self.suservo_device is None or self.suservo_channel is None:
            raise ValueError(
                "suservo_device or suservo_channel is None. You must either pass these to build_fragment()"
                " or call set_settings() before Fragment setup"
            )

        super().host_setup()
        self.core: Core = self.get_device("core")

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.suservo_device.init()
        self.suservo_device.set_config(enable=1)

    @kernel
    def read_adc(self):
        return self.suservo_device.get_adc(self.suservo_channel)
