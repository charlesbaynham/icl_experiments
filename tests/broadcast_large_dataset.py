import logging

import numpy as np
from artiq.experiment import *

logger = logging.getLogger(__name__)


class BroadcastLargeDataset(EnvExperiment):
    def build(self):
        self.set_dataset("large_dataset", [], broadcast=True, archive=False)

        self.setattr_argument(
            "num_10mb_chunks",
            NumberValue(1, min=1, step=1, scale=1, type="int"),
            tooltip="Number of 10MB chunks to broadcast",
        )

    def run(self):
        logger.info(
            "Starting broadcast of large dataset with %d chunks", self.num_10mb_chunks
        )

        for i in range(self.num_10mb_chunks):
            logger.info("Broadcasting chunk %d/%d", i + 1, self.num_10mb_chunks)

            # Create a 10MB list of numbers
            large_data = (
                np.random.rand(10 * 1024 * 1024 // 8).astype(np.float64).tolist()
            )

            self.append_to_dataset("large_dataset", large_data)
