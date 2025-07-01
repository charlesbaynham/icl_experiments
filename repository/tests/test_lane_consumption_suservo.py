import logging

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import *
from artiq.language import delay

logger = logging.getLogger(__name__)

# Hypothesis: the SUServo code is consuming more than one lane when `set_iir_mu`
# is called.


class TestSUServoLaneUsage(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "num", NumberValue(default=9, type="int", precision=0, scale=1, step=1)
        )
        self.num: int

        self.setattr_argument(
            "suservo_channel",
            StringValue(default="suservo_aom_singlepass_461_imaging_delivery"),
        )

        self.suservo_channel: SUServoChannel = self.get_device(self.suservo_channel)
        self.suservo: SUServo = self.suservo_channel.servo

        self.setattr_device("ttl1")  # This is currently unused and is on the master
        self.ttl: TTLOut = self.ttl1

    @kernel
    def run(self):
        logger.info("Starting test")

        self.core.reset()

        # Safety first
        self.suservo_channel.set(
            en_out=0,
            en_iir=0,
            profile=0,
        )

        delay(500e-3)  # Make loads of slack

        # Do an IIR write twice, consuming at least one lane, maybe more
        self.suservo_channel.set_iir(0, 0, 0.0)
        self.suservo_channel.set_iir(0, 0, 0.0)

        for i in range(self.num):
            # Write in backwards order to ensure that we use a new lane each time
            delay(-1e-3)
            self.ttl.set_o(bool(i % 2))
            print(i)

        logger.info("Test done")
