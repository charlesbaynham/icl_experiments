import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import *

logger = logging.getLogger(__name__)


class KernelSpeedTest(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "n",
            NumberValue(
                default=1000, unit="", scale=1, step=1, precision=0, type="int"
            ),
        )

    @rpc
    def get_random_numbers(self) -> np.ndarray:
        return np.random.rand(self.n)

    @kernel
    def run(self):
        output = [0.0] * self.n

        numbers_a = self.get_random_numbers()
        numbers_b = self.get_random_numbers()

        # Do a non-trivial calculation on the code
        t_start_mu = self.core.get_rtio_counter_mu()
        for i in range(self.n):
            output[i] = numbers_a[i] * numbers_b[i]

        t_end_mu = self.core.get_rtio_counter_mu()

        logger.info(
            "Kernel time: %.3f us for %i FLOP",
            (1e6 * self.core.mu_to_seconds(t_end_mu - t_start_mu)),
            self.n,
        )

        logger.debug("Random numbers: %s", output)
