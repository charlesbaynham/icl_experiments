import logging
import time

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue

from repository.lib.tasmota_crates import confirm_with_code
from repository.lib.tasmota_crates import power_off_all
from repository.lib.tasmota_crates import power_on_all

logger = logging.getLogger(__name__)

DATASET_NAME = "reboot_code"


class HardRebootARTIQCrates(EnvExperiment):
    "Hard reboot the artiq crates by power cycling them"

    def build(self):
        self.setattr_argument(
            "confirmation_code",
            NumberValue(default=-1, precision=0, scale=1, step=1, min=0, type="int"),
        )
        self.confirmation_code: int

    def run(self):
        if not confirm_with_code(self, DATASET_NAME):
            return

        logger.warning("Rebooting ARTIQ crates now")
        power_off_all()
        time.sleep(3)
        power_on_all()
