import re

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import BooleanValue
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue


class SetDDS(EnvExperiment):
    """Set a DDS channel"""

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "frequency",
            NumberValue(default=20e6, unit="MHz", step=0.1e6, ndecimals=1, min=0),
        )
        self.setattr_argument(
            "attenuation",
            NumberValue(default=0, unit="dB", step=0.1, ndecimals=1, min=0),
        )
        self.setattr_argument(
            "switch_status",
            BooleanValue(default=True),
        )

        urukuls = [
            k for k in self.get_device_db().keys() if re.match(r"urukul\d_ch\d", k)
        ]

        self.setattr_argument("dds_id", EnumerationValue(urukuls))

        self.dds = self.get_device(self.dds_id)

    @kernel
    def run(self):
        self.core.reset()

        dds = self.dds  # type: AD9912

        dds.init()
        dds.set(self.frequency, 0.0)
        dds.set_att(self.attenuation)
        dds.sw.set_o(self.switch_status)
