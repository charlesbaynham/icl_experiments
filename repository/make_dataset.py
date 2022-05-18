import logging
from datetime import datetime

from artiq.experiment import EnvExperiment

logger = logging.getLogger(__name__)


class DataWriter(EnvExperiment):
    """Make some data"""

    def build(self):
        pass

    def run(self):
        self.set_dataset("my_data", f"This is my data! I ran at {datetime.utcnow()}")
