from artiq.coredevice.ttl import TTLOut
from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel


class WriteTTL(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.ttl: TTLOut = self.get_device("ttl_urukul2_sw2")

        self.setattr_argument("state", BooleanValue(default=True))

    @kernel
    def run(self):
        self.core.break_realtime()
        self.ttl.set_o(self.state)
