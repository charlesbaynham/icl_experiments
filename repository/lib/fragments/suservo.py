from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import kernel
from artiq.experiment import TBool
from artiq.experiment import TFloat
from ndscan.experiment import Fragment

from repository.lib.fragments.debug_logger import DebugLogger


class LibSetSUServoStatic(Fragment):
    """
    Set a static SUServo output

    The channel to be set should be passed as an argument to :meth:`.build_fragment`, e.g.::

        self.setattr_fragment(
            "LibSetSUServoStatic", LibSetSUServoStatic, "suservo0_ch0",
        )

    The :meth:`~ndscan.experiment.fragment.Fragment.device_setup` of this
    :class:`~ndscan.experiment.fragment.ExpFragment` will reinitialise the
    entire SUServo device. This Fragment then provides a :meth:`.set_suservo`
    method which can be used to set the specified channel's output.
    """

    def build_fragment(self, channel: str):
        self.setattr_device("core")
        self.core: Core

        self.channel = channel

        self.suservos_have_been_initiated = False

        self.setattr_fragment("logger", DebugLogger, "suservo")
        self.logger: DebugLogger

    def host_setup(self):
        super().host_setup()

        self.suservo_channel: Channel = self.get_device(self.channel)
        self.suservo: SUServo = self.suservo_channel.servo

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Initiate the suservo itself (i.e. all four channels)
        if not self.suservos_have_been_initiated:
            self.core.break_realtime()

            self.suservo.init()
            self.suservos_have_been_initiated = True

            # Read the attenuator registers so that we don't affect other channels
            for cpld in self.suservo.cplds:
                att_mu = cpld.get_att_mu()
                self.logger.log("Attenuation reg: 0x%X", att_mu)

    @kernel
    def set_suservo(
        self,
        freq: TFloat,
        amplitude: TFloat,
        attenuation: TFloat = 30.0,
        rf_switch_state: TBool = True,
    ):
        """Set a static output on a SUServo channel

        This method consumes no slack unless the logging level is in DEBUG mode,
        in which case it calls
        :meth:`~artiq.coredevice.core.Core.break_realtime`.

        Args:
            freq (TFloat): Frequency in Hz amplitude (TFloat): Amplitude from 0
            to 1 when 1 is 100% output. attenuation (TFloat, optional):
            Attenuation on the variable attenuator. Defaults to 30.0.
        """
        # type:(Channel, float, float, float) -> None

        self.logger.log(
            "Setting channel %s to %f MHz, amp = %f, att = %f",
            self.channel,
            1e-6 * freq,
            amplitude,
            attenuation,
        )

        # Set the attenuator for this channel on this Urukul
        attenuator_channel = self.suservo_channel.servo_channel % 4
        cpld = self.suservo_channel.dds.cpld  # type: CPLD
        cpld.set_att(attenuator_channel, attenuation)

        # Configure profile 0 to have the requested amplitude and frequency
        self.suservo_channel.set_y(profile=0, y=amplitude)
        self.suservo_channel.set_dds(
            profile=0,
            offset=-0.5,  # Not used
            frequency=freq,
            phase=0.0,
        )

        # Enable profile 0 and the suservo more widely
        self.suservo_channel.set(
            en_out=(1 if rf_switch_state else 0), en_iir=0, profile=0
        )
        self.suservo.set_config(enable=1)
