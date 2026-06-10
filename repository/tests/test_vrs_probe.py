import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.vrs_probe_ramper import VRS_Probe_Ramper

logger = logging.getLogger(__name__)

URUKUL = "urukul_squeezing_probe"


class TestVRSProbeRamperFrag(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device(URUKUL)
        self.dds: AD9910

        self.setattr_fragment("probe_ramper", VRS_Probe_Ramper, URUKUL)
        self.probe_ramper: VRS_Probe_Ramper

    @kernel
    def run_once(self) -> None:
        self.core.reset()
        delay(100e-3)
        self.dds.init()

        self.core.break_realtime()

        self.probe_ramper.trigger()
        delay(10.0)
        self.probe_ramper.stop()
        logger.info("Probe ramp: %f" % self.probe_ramper.dF_dt)
        logger.info("Probe max frequency: %f" % self.probe_ramper.max_f)
        logger.info("Probe min frequency: %f" % self.probe_ramper.min_f)


TestVRSProbeRamper = make_fragment_scan_exp(
    TestVRSProbeRamperFrag, max_rtio_underflow_retries=0
)
