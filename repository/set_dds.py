from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel


class SetDDS(EnvExperiment):
    def build(self):
        self.setattr_device("core")

        urukuls = [k for k in self.get_device_db().keys() if "urukul" in k]

        self.setattr_argument("dds_id", EnumerationValue(urukuls))

        self.dds = self.get_device(self.dds_id)

    @kernel
    def run(self):
        self.core.reset()

        dds = self.dds  # type: AD9912

        dds.init()
        dds.set(10e6, 0.0)
        dds.set_att(0.0)
        dds.sw.on()
