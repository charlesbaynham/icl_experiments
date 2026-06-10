import logging

from RsInstrument import *
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
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
        # devices
        self.setattr_device("core")
        self.core: Core

        self.dds: AD9910 = self.get_device(URUKUL)
        self.setattr_device
        # Params

        # Fragments
        self.setattr_fragment("probe_ramper", VRS_Probe_Ramper, URUKUL)
        self.probe_ramper: VRS_Probe_Ramper

        # Variable

        # Invariants
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dds")

    @kernel
    def run_once(self) -> None:
        self.core.reset()
        delay(100e-3)
        self.dds.init()

        self.core.break_realtime()

        self.probe_ramper.trigger()
        delay(10.0)
        self.probe_ramper.stop()
        logger.info("Probe ramp: %f", self.probe_ramper.dF_dt.get())
        logger.info("Probe max frequency: %f", self.probe_ramper.max_f.get())
        logger.info("Probe min frequency: %f", self.probe_ramper.min_f.get())


class TestRTBSetupFrag(ExpFragment):

    def build_fragment(self):
        # devices
        self.setattr_device("core")
        self.core: Core

        # setup the TTL
        # FILL IN WITH THE CORRECT NAME!
        self.ttl = self.get_device("ttl_shutter_repump_707")
        self.ttl: TTLOut

        self.rtb = RsInstrument("TCPIP::10.137.1.19::INSTR", id_query=True, reset=True)
        # Set the trigger to an external signal
        self.rtb.write_str("TRIG:A:SOUR EXT")
        # Set the trigger to be the positive edge
        self.rtb.write_str("TRIG:A:TYPE EDGE")
        self.rtb.write_str("TRIG:A:EDGE:SLOP POS")
        # Set the trigger height to be 3 V
        self.rtb.write_str("TRIG:A:LEV5 3")

        # Set the acquisition settings CH1 is the PMT signal
        self.rtb.write_str("TIM:ACQT 0.01")  # 10ms Acquisition time
        self.rtb.write_str("CHAN1:RANG 5.0")  # Horizontal range 5V (0.5V/div)
        self.rtb.write_str("CHAN1:OFFS 0.0")  # Offset 0
        self.rtb.write_str("CHAN1:STAT ON")  # Switch Channel 1 ON

    def run_once(self) -> None:
        # Pulse the TTL for 10 ms
        self.ttl.pulse(10e-3)
        delay(10e-3)


TestVRSProbeRamper = make_fragment_scan_exp(
    TestVRSProbeRamperFrag, max_rtio_underflow_retries=0
)

TestRTBSetup = make_fragment_scan_exp(TestRTBSetupFrag)
