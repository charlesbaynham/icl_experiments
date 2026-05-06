import logging

from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment

from repository.lib.tasmota_crates import power_on_all

logger = logging.getLogger(__name__)


class StartARTIQCrates(EnvExperiment):
    "Start the artiq crates by powering them on"

    def build(self):
        self.setattr_argument(
            "include_oven",
            BooleanValue(default=False),
        )
        self.include_oven: bool

    def run(self):
        logger.warning("Starting ARTIQ crates now")
        power_on_all(include_oven=self.include_oven)
