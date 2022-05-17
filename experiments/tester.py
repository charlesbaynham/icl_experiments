import logging

import artiq
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue

logger = logging.getLogger(__name__)


class Tester(EnvExperiment):
    def build(self):
        pass

    def run(self):
        logger.info(
            "Hello world! I'm an experiment running on ARTIQ version %s",
            artiq.__version__,
        )

        logger.warning(
            'Most experiments output print statements at the "INFO" level. To see this, set your log level to "INFO" or less'
        )
