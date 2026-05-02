import logging

from artiq.experiment import EnvExperiment

from repository.lib.tasmota_crates import power_on_all

logger = logging.getLogger(__name__)


class StartARTIQCrates(EnvExperiment):
    "Start the artiq crates by powering them on"

    def build(self):
        pass

    def run(self):
        logger.warning("Starting ARTIQ crates now")
        power_on_all()
