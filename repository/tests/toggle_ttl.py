import logging

from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment
from artiq.experiment import StringValue
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu

logger = logging.getLogger(__name__)


class ToggleTTL(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument("ttl_device", StringValue())

    def run(self):
        self.ttl = self.get_device(self.ttl_device)

        print("Starting toggling")

        self.toggle()

        print("Toggling completed")

    @kernel
    def toggle(self):
        self.core.reset()
        for _ in range(20):
            self.ttl.on()
            delay(1.0)
            self.ttl.off()
            delay(1.0)

        self.core.wait_until_mu(now_mu())
