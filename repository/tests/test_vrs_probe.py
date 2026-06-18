import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import OpaqueChannel
from ndscan.experiment import ResultChannel
from ndscan.experiment import delay
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from RsInstrument import RsInstrument

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

        self.rtb_data = float

        self.setattr_param(
            "acquisition_time",
            FloatParam,
            "Scope Acquisition Time",
            default=0.3,
            unit="ms",
            min=0.0,
        )
        self.acquisition_time: FloatParamHandle

        self.setattr_result("scope_data", OpaqueChannel)
        self.scope_data: ResultChannel

        # setup the TTL
        self.ttl = self.get_device("ttl_vrs_scope_trigger")
        self.ttl: TTLOut

        ### This stuff should not be done in build fragment but probably somewhere later... needs to be done from the computer

    @host_only
    def host_setup(self):
        self.rtb = RsInstrument("TCPIP::10.137.1.19::INSTR", id_query=False, reset=True)
        # Set the trigger to an external signal
        self.rtb.write_str("TRIG:A:SOUR EXT")
        # Set the trigger to be the positive edge
        self.rtb.write_str("TRIG:A:TYPE EDGE")
        self.rtb.write_str("TRIG:A:EDGE:SLOP POS")
        # Set the trigger height to be 1 V
        self.rtb.write_str("TRIG:A:LEV5 1")

        # Set the acquisition settings CH1 is the PMT signal
        self.rtb.write_float(
            "TIM:ACQT", self.acquisition_time.get()
        )  # Scope Acquisition time
        self.rtb.write_float("CHAN1:RANG", 5.0)  # Total Vertical range 5V (0.5V/div)
        self.rtb.write_float("CHAN1:OFFS", 0.0)  # Offset 0
        self.rtb.write_bool("CHAN1:STAT", True)  # Switch Channel 1 ON
        # Sample Data, we want the max of 20 MSa per segment
        self.rtb.write_float("ACQ:POIN", 20e6)
        # Setup a single shot
        self.rtb.write_str("SING")
        self.rtb.query("*OPC?")

    @kernel
    def run_once(self) -> None:
        # Pulse the TTL for 10 ms
        logger.info("Begin the pulse")
        self.core.break_realtime()
        self.ttl.pulse(1e-3)
        self.core.break_realtime()
        logger.info("start the wait")
        delay(self.acquisition_time.get())

        # Get the data from the scope and save it in the results channel
        self.get_data_from_scope()
        logger.info("I've gotten data!")

    # Does this need to be done on the PC?, how else would it manage to save the data
    # Also this is quite a large data set...
    # We can save this data on the scope internally and rerun the experiment
    @rpc
    def get_data_from_scope(self):
        # Save the data in ascii format and save
        # data = self.rtb.query_bin_or_ascii_float_list(
        #     "FORM ASC;:CHAN1:DATA:POINT MAX;:CHAN1:DATA?"
        # )
        logger.info("Query")
        data = self.rtb.query_bin_or_ascii_float_list("FORM ASC;:CHAN1:DATA?")

        # data = self.rtb.query_bin_or_ascii_float_list("CHAN1:DATA:HEADer?")
        self.core.break_realtime()
        logger.info("Data Here")

        self.scope_data.push(data)
        logger.info("Pushed")
        # self.set_dataset("scope_data", data, broadcast=True, archive=False)


TestVRSProbeRamper = make_fragment_scan_exp(
    TestVRSProbeRamperFrag, max_rtio_underflow_retries=0
)

TestRTBSetup = make_fragment_scan_exp(TestRTBSetupFrag)
