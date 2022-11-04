import logging
import re

from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import kernel
from artiq.experiment import TFloat
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import StringParam
from ndscan.experiment.entry_point import make_fragment_scan_exp


class SetSUServoStatic(ExpFragment):
    """
    Set a static SUServo output

    The channel to be set should be configured using
    :meth:`.Fragment.override_param` or :meth:`.Fragment.bind_param`.

    The :meth:`.Fragment.device_setup` of this ExpFragment will reinitialise the
    entire SUServo device. This Fragment then provides a :meth:`.set_suservo`
    method which can be used to set the specified channel's output (and which
    ignores the "frequency", "amplitude" etc parameters). The :meth:`.run_once`
    method just calls :meth:`.set_suservo` using the parameters.

    FIXME: This Fragment currently sets all channels on the same Urukul to have
    the same attenuation as the desired one. This is obviously a problem.
    """

    def build_fragment(self):
        self.setattr_device("core")

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
        self.setattr_param(
            "channel",
            StringParam,
            description="SUServo channel to set",
            default='"' + suservo_channels[0] + '"',
        )

    def host_setup(self):
        self.suservo_channel: Channel = self.get_device(self.channel.get())
        self.suservo: SUServo = self.suservo_channel.servo

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Initiate the suservo itself (i.e. all four channels)
        self.core.break_realtime()
        self.suservo.init()

    @kernel
    def set_suservo(
        self,
        freq: TFloat,
        amplitude: TFloat,
        attenuation: TFloat = 30.0,
    ):
        # type:(Channel, float, float, float) -> None

        logging.info(
            "Setting channel %s to %f MHz, amp = %f, att = %f",
            self.suservo_channel,
            1e-6 * freq,
            amplitude,
            attenuation,
        )

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

    @kernel
    def run_once(self):
        self.set_suservo(
            self.frequency.get(), self.amplitude.get(), self.attenuation.get()
        )


SetSUServoStaticExp = make_fragment_scan_exp(SetSUServoStatic)
