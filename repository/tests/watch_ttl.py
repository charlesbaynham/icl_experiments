from artiq.coredevice.ttl import TTLInOut
from artiq.experiment import EnvExperiment, BooleanValue, NumberValue
from artiq.language.core import kernel, delay
import logging

logger = logging.getLogger(__name__)


class WriteTTL(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.ttl: TTLInOut = self.get_device("ttl_urukul2_sw2")

        self.setattr_argument("state", BooleanValue(default=True))
        self.state: bool

        self.setattr_argument("watch_time", NumberValue(unit="s", default=1.0))
        self.watch_time: float

    @kernel
    def run(self):
        self.core.break_realtime()
        if self.state:
            self.ttl.watch_stay_on()
        else:
            self.ttl.watch_stay_off()
        delay(self.watch_time)
        result = self.ttl.watch_done()
        logger.info("TTL stayed %s: %s", self.state, result)
