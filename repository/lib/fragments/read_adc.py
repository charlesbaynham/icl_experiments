from typing import Optional

from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import StringParam
from ndscan.experiment.parameters import StringParamHandle


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

    def build_fragment(
        self,
        sampler_device: Optional[Sampler] = None,
        sampler_channel: Optional[int] = None,
    ):
        """
        Build this (sub)fragment

        If sampler_device and sampler_channel are provided then this fragment will have no parameters.
        Otherwise, it will expose these as ndscan parameters instead.
        """
        if sampler_channel is not None and sampler_channel is not None:
            self.sampler_channel: int = sampler_channel
            self.sampler_device: Sampler = sampler_device
        else:
            self.setattr_param(
                "sampler_channel_number",
                IntParam,
                description="Sampler channel to read",
                default=0,
                min=0,
                max=7,
            )
            self.setattr_param(
                "sampler_device_name",
                StringParam,
                description="Sampler device to read",
                default="",
            )
            self.sampler_device_name: StringParamHandle

        self.core: Core = self.get_device("core")

    def host_setup(self):
        if hasattr(self, "sampler_channel_number"):
            self.sampler_device = self.get_device(self.sampler_device_name.get())
            self.sampler_channel = self.sampler_channel_number.get()
        super().host_setup()

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

    The channel to be read is passed as arguments to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "ReadSUServoADC", ReadSUServoADC, my_suservo_channel
        )
    """

    def build_fragment(
        self, suservo_channel: SUServoChannel, suservo_profile_number: int = -1
    ):
        self.setattr_device("core")
        self.core: Core

        self.suservo_channel: SUServoChannel = suservo_channel
        self.suservo_profile_number = suservo_profile_number

    def host_setup(self):
        super().host_setup()

        self.suservo_channel_number: int = self.suservo_channel.servo_channel
        self.suservo_device: SUServo = self.suservo_channel.servo

        # If suservo profile was not passed, assume the AION convention that the
        # profile == the channel number
        if self.suservo_profile_number == -1:
            self.suservo_profile_number = self.suservo_channel_number

        self.suservo_has_been_setup = False

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        if not self.suservo_has_been_setup:
            self.core.break_realtime()
            self.suservo_device.init()
            self.suservo_device.set_config(enable=1)
            self.suservo_has_been_setup = True

    @kernel
    def read_adc(self):
        return self.suservo_device.get_adc(self.suservo_channel_number)

    @kernel
    def read_ctrl_signal(self):
        return self.suservo_channel.get_y(self.suservo_profile_number)
