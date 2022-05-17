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
        logger.debug(
            "This is a DEBUG message - you'll only see this level of detail if you select DEBUG as your logging level."
        )

        logger.info(
            "Hello world! I'm an experiment running on ARTIQ version %s",
            artiq.__version__,
        )

        logger.warning(
            "This is a WARNING level message, visible for all log levels below WARNING."
        )

        logger.error(
            "This is an ERROR level message - these will almost always be visible"
        )

        logger.critical("This is a CRITICAL message - these cannot be hidden")
