import logging

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import kernel
from artiq.experiment import RTIOUnderflow
from artiq.experiment import TFloat
from ndscan.experiment import Fragment


logger = logging.getLogger(__name__)


class LibSetSUServoStatic(Fragment):
    """
    Set a static SUServo output

    The channel to be set should be configured using
    :meth:`~ndscan.experiment.fragment.Fragment.override_param` or
    :meth:`~ndscan.experiment.fragment.Fragment.bind_param`.

    The :meth:`~ndscan.experiment.fragment.Fragment.device_setup` of this
    :class:`~ndscan.experiment.fragment.ExpFragment` will reinitialise the
    entire SUServo device. This Fragment then provides a :meth:`.set_suservo`
    method which can be used to set the specified channel's output.

    FIXME: This Fragment currently sets all channels on the same Urukul to have
    the same attenuation as the desired one. This is obviously a problem.
    """

    def build_fragment(self, channel: str):
        self.setattr_device("core")
        self.core: Core

        self.channel = channel

    def host_setup(self):
        self.suservo_channel: Channel = self.get_device(self.channel)
        self.suservo: SUServo = self.suservo_channel.servo

        self.print_debug_statements = logger.isEnabledFor(logging.DEBUG)

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Initiate the suservo itself (i.e. all four channels)
        try:
            self.suservo.init()
        except RTIOUnderflow:
            self.core.break_realtime()
            self.suservo.init()

    @kernel
    def set_suservo(
        self,
        freq: TFloat,
        amplitude: TFloat,
        attenuation: TFloat = 30.0,
    ):
        """Set a static output on a SUServo channel

        This method consumes no slack unless the logging level is in DEBUG mode, in which case it calls :meth:`~artiq.coredevice.core.Core.break_realtime`.

        Args:
            freq (TFloat): Frequency in Hz
            amplitude (TFloat): Amplitude from 0 to 1 when 1 is 10)% output.
            attenuation (TFloat, optional): Attenuation on the variable attenuator. Defaults to 30.0.
        """
        # type:(Channel, float, float, float) -> None

        if self.print_debug_statements:
            logger.info(
                "Setting channel %s to %f MHz, amp = %f, att = %f",
                self.channel,
                1e-6 * freq,
                amplitude,
                attenuation,
            )
            self.core.break_realtime()

        # Set the attenuator for all channels on this Urukul
        cpld = self.suservo_channel.dds.cpld  # type: CPLD
        attenuation_mu = cpld.att_to_mu(attenuation)
        att_reg = (
            attenuation_mu
            | (attenuation_mu << 1 * 8)
            | (attenuation_mu << 2 * 8)
            | (attenuation_mu << 3 * 8)
        )
        cpld.set_all_att_mu(att_reg)

        # Configure profile 0 to have the requested amplitude and frequency
        self.suservo_channel.set_y(profile=0, y=amplitude)
        self.suservo_channel.set_dds(
            profile=0,
            offset=-0.5,  # Not used
            frequency=freq,
            phase=0.0,
        )

        # Enable profile 0 and the suservo more widely
        self.suservo_channel.set(en_out=1, en_iir=0, profile=0)
        self.suservo.set_config(enable=1)
