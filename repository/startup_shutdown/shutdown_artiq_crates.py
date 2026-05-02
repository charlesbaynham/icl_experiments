import logging

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue

from repository.lib.tasmota_crates import confirm_with_code
from repository.lib.tasmota_crates import power_off_all

logger = logging.getLogger(__name__)

DATASET_NAME = "shutdown_code"


class ShutdownARTIQCrates(EnvExperiment):
    "Shut down the artiq crates by powering them off"

    def build(self):
        self.setattr_argument(
            "confirmation_code",
            NumberValue(default=-1, precision=0, scale=1, step=1, min=0, type="int"),
        )
        self.confirmation_code: int

    def run(self):
        if not confirm_with_code(self, DATASET_NAME):
            return

        logger.warning("Shutting down ARTIQ crates now")
        power_off_all()
