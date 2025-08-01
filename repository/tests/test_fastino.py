from artiq.coredevice.core import Core
from artiq.coredevice.fastino import Fastino
from artiq.language.core import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle


class FastinoControlFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("fastino0")
        self.fastino0: Fastino
        self.setattr_param(
            "voltage", FloatParam, description="Voltage", default=0.0, unit="V"
        )
        self.voltage: FloatParamHandle

        self.setattr_param("channel", IntParam, description="Channel", default=0)
        self.channel: IntParamHandle

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.fastino0.init()

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.fastino0.set_dac(self.channel.get(), self.voltage.get())


FastinoControl = make_fragment_scan_exp(FastinoControlFrag)
