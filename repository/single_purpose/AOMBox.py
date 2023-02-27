import logging
import re

from artiq.coredevice import suservo
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.master.scheduler import Scheduler


class AOMBox(EnvExperiment):
    """Get the AOM Box working"""

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "frequency",
            NumberValue(default=20, unit="MHz", step=0.1e6, ndecimals=1, min=0),
        )
        self.setattr_argument(
            "frequency", NumberValue(default=0, unit="dB", step=0.1, ndecimals=1, min=0)
        )

        available = [
            k for k in self.get_device_db().keys() if re.match(r"suservo0_ch\d", k)
        ]
        print(available)
        self.setattr_argument("dds", EnumerationValue(available))

    # @kernel
    def run(self):
        self.core.reset()

        dds = self.dds
        dds.init()
