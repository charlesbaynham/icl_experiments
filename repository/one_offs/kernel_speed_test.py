import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import *
from ndscan.experiment import *

logger = logging.getLogger(__name__)


class KernelSpeedTestFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.n = self.setattr_param(
            "n",
            IntParam,
            default=1000,
            description="Number of random numbers to generate",
        )

        self.time_taken = self.setattr_result("time_taken", FloatChannel)
        self.flops = self.setattr_result("flops", FloatChannel)

    @rpc
    def get_random_numbers(self, n) -> list[float]:
        return np.random.rand(n).tolist()

    @kernel
    def run_once(self):
        n = self.n.get()
        output = [0.0] * n

        numbers_a = self.get_random_numbers(n)
        numbers_b = self.get_random_numbers(n)

        # Do a non-trivial calculation on the code
        t_start_mu = self.core.get_rtio_counter_mu()
        for i in range(n):
            output[i] = numbers_a[i] * numbers_b[i]

        t_end_mu = self.core.get_rtio_counter_mu()

        time_taken = self.core.mu_to_seconds(t_end_mu - t_start_mu)

        logger.info(
            "Kernel time: %.3f us for %i FLOP",
            1e6 * time_taken,
            n,
        )

        logger.debug("Random numbers: %s", output)

        self.time_taken.push(time_taken)
        self.flops.push(float(n) / time_taken)


KernelSpeedTest = make_fragment_scan_exp(KernelSpeedTestFrag)
