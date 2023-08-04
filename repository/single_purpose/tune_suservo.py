import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.experiment import parallel
from artiq.experiment import TBool
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from pyaion.lib.utils import get_local_devices


logger = logging.getLogger(__name__)

PROFILE_NUM = 0


class TuneSUServo(EnvExperiment):
    """
    Tune a SUServo output
    """

    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "channel_name", EnumerationValue(get_local_devices(self, Channel))
        )
        self.setattr_argument(
            "adc_channel",
            NumberValue(default=0, scale=1, ndecimals=0, step=1, type="int"),
        )

        self.setattr_argument(
            "frequency",
            NumberValue(default=100e6, ndecimals=1, type="float", unit="MHz"),
        )
        self.setattr_argument(
            "attenuation",
            NumberValue(default=30.0, ndecimals=1, type="float", unit="dB"),
        )

        self.setattr_argument(
            "num_points",
            NumberValue(default=0, scale=1, ndecimals=0, step=1, type="int"),
        )

    def prepare(self):
        self.suservo_channel: Channel = self.get_device(self.channel_name)
        self.suservo: SUServo = self.suservo_channel.servo

    @kernel
    def run(self):
        # Initiate the suservo itself (i.e. all four channels)

        self.core.reset()
        self.suservo.init()

        self.set_all_attenuations(30.0)
        self.set_this_attenuation(self.attenuation)

        self.set_dds_params(self.frequency, 1.0, False)

        self.suservo_channel.set(en_out=1, en_iir=1, profile=PROFILE_NUM)

        self.set_dataset("voltages", [0.0])

        for _ in range(self.num_points):
            delay(100e-3)
            self.append_to_dataset("voltages", self.suservo_channel.get_y(PROFILE_NUM))

    @kernel
    def set_all_attenuations(self, attenuation: TFloat):
        """
        Set all channels on the same DDS as this channel to the same, given
        attenuation

        This is annoyingly required because there is no way of getting
        information out from the SUServo gateware about the current settings, so
        they have to be reset on each run.
        """
        logger.warning(
            "Setting the attenuator for all channels on Urukul %s",
            self.suservo_channel.dds,
        )

        self.core.break_realtime()
        cpld = self.suservo_channel.dds.cpld  # type: CPLD
        cpld.get_att_mu()
        attenuation_mu = cpld.att_to_mu(attenuation)
        att_reg = (
            attenuation_mu
            | (attenuation_mu << 1 * 8)
            | (attenuation_mu << 2 * 8)
            | (attenuation_mu << 3 * 8)
        )
        self.core.break_realtime()
        cpld.set_all_att_mu(att_reg)

    @kernel
    def set_this_attenuation(self, attenuation: TFloat):
        # Set the attenuator for this channel on this Urukul
        attenuator_channel = self.suservo_channel.servo_channel % 4
        cpld = self.suservo_channel.dds.cpld  # type: CPLD
        cpld.set_att(attenuator_channel, attenuation)

    @kernel
    def set_dds_params(
        self, frequency: TFloat, amplitude: TFloat, rf_switch_state: TBool
    ):
        # Configure profile 0 to have the requested amplitude and frequency
        self.suservo_channel.set_y(profile=0, y=amplitude)
        self.suservo_channel.set_dds(
            profile=PROFILE_NUM,
            offset=-0.5,  # Not used
            frequency=frequency,
            phase=0.0,
        )

        # Enable profile 0 and the suservo more widely
        self.suservo_channel.set(
            en_out=(1 if rf_switch_state else 0), en_iir=0, profile=PROFILE_NUM
        )
