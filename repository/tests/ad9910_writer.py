import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue


logger = logging.getLogger(__name__)


class AD9910Writer(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("urukul5_ch0")
        self.urukul5_ch0: AD9910

        self.dds = self.urukul5_ch0

        self.setattr_argument("freq", NumberValue(default=10e6, unit="MHz"))

    @kernel
    def run(self):
        self.core.reset()
        self.dds.init(blind=False)

        delay(10e-3)

        self.core.break_realtime()
        self.dds.set(self.freq)
        self.dds.sw.on()
