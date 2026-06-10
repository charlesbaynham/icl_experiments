import logging

from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.vrs_probe_ramper import VRS_Probe_Ramper

logger = logging.getLogger(__name__)


class TestVRSProbeRamperFrag(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "probe_ramper",
            VRS_Probe_Ramper,
            # I need an ad9910 name
        )
        self.probe_ramper: VRS_Probe_Ramper

    @kernel
    def run_once(self) -> None:
        self.probe_ramper.trigger()
        self.delay(10.0)
        self.probe_ramper.stop()


TestVRSProbeRamper = make_fragment_scan_exp(
    TestVRSProbeRamperFrag, max_rtio_underflow_retries=0
)
