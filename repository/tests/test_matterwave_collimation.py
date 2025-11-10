import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from pyaion.fragments.urukul_init import make_urukul_init

from repository.lib.experiment_templates.mixins.painted_quadratic import PaintedQuadraticMixin
from repository.lib.fragments.painted_pulse import DiffractionCompensatedQuadratic

PAINTING_URUKUL_CHANNEL = "urukul9910_aom_1064_painting"
logger = logging.getLogger(__name__)


class TestMatterwaveCollimationInDipoleTrapFrag(
    PaintedQuadraticMixin
    ):

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.dds.sw.off()

        # This is an arbitrary frequency - it will be overwritten by the pulse
        self.dds.set(frequency=10e6, amplitude=0.1)
        self.dds.set_att(0.0)
        self.core.break_realtime()
        self.painter.prepare_pulse()
        self.core.break_realtime()
        self.painter.start_output()
        logger.warning("The pulse duration: ", self.dds.read64(0x15))
        logger.warning("Hey I'm starting minute")
        logger.warning("The mu: ", self.painter._step_mu)

        delay(10.0)
        self.painter.stop_output()

        self.core.wait_until_mu(now_mu())
        logger.warning("Hey it's been a minute")


TestMatterwaveCollimationInDipoleTrap = make_fragment_scan_exp(
    TestMatterwaveCollimationInDipoleTrap, max_rtio_underflow_retries=0
)
