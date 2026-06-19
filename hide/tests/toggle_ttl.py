import logging

from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment
from artiq.experiment import StringValue
from artiq.language import delay
from artiq.language import kernel
from artiq.master.scheduler import Scheduler

logger = logging.getLogger(__name__)


class ToggleTTL(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument("ttl_device", StringValue())

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

    def run(self):
        self.ttl = self.get_device(self.ttl_device)

        print("Starting toggling")

        self.toggle()

        print("Toggling completed")

    @kernel
    def toggle(self):
        self.core.reset()
        state = False

        while True:
            self.ttl.set_o(state)
            state = not state
            delay(1.0)
            if self.scheduler.check_pause():
                return
