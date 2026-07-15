import logging

from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment

logger = logging.getLogger(__name__)


class DemoExperiment(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

    def run(self):
        print("Hello I'm a test")
