from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from ndscan.experiment import *
from pyaion.fragments.urukul_init import make_urukul_init

from repository.lib.fragments.painted_pulse import DiffractionCompensatedQuadratic

PAINTING_URUKUL_CHANNEL = "urukul9910_aom_1064_painting"


class TestDiffractionCompensatedQuadratic(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "urukul_init", make_urukul_init([PAINTING_URUKUL_CHANNEL])
        )

        self.dds: AD9910 = self.get_device(PAINTING_URUKUL_CHANNEL)

        self.setattr_fragment("painter", DiffractionCompensatedQuadratic)
        self.painter: DiffractionCompensatedQuadratic

        self.ttl_trigger: TTLOut = self.get_device("ttl_shutter_debugging_trigger")

    def run_once(self) -> None:
        self.core.break_realtime()
        self.dds.sw.off()
        # This is an arbitrary frequency - it will be overwritten by the pulse
        self.dds.set(frequency=100e6, amplitude=1.0)

        self.core.break_realtime()
        self.painter.prepare_pulse()

        self.core.break_realtime()
        self.painter.trigger_pulse()

        # FIXME THese functions need to exist
        self.painter.start_output()
        delay(1.0)
        self.painter.stop_output()
