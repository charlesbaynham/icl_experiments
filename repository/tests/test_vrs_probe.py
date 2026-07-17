import logging

import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.urukul import CPLD
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from artiq.master.worker_impl import CCB
from ndscan.experiment import ExpFragment
from ndscan.experiment import OpaqueChannel
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from RsInstrument import RsInstrument

from repository.lib.devices.rigol_dho_scope import RigolDHO
from repository.lib.devices.rohde_schwarz_devices import RSDevice
from repository.lib.fragments.vrs_probe_ramper import VRS_Probe_Ramper

logger = logging.getLogger(__name__)

URUKUL = "urukul9910_squeezing_probe"


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
        self.setattr_param(
            "attenuation",
            FloatParam,
            "DDS attenuation",
            min=0,
            max=30,
            default=30,
            unit="dB",
        )
        self.attenuation: FloatParamHandle

        # Invariants
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dds")

    @host_only
    def host_setup(self):
        super().host_setup()

        # Set the CPLD
        self.cpld: CPLD = self.dds.cpld

    @kernel
    def device_setup(self) -> None:
        print("Hello")
        self.core.break_realtime()
        delay(200e-3)
        self.cpld.init()
        self.dds.init()
        delay(1e-3)
        self.dds.sw.set_o(True)
        self.dds.set_att(self.attenuation.get())
        self.dds.set(self.probe_ramper.min_f.get())
        self.core.break_realtime()

        self.device_setup_subfragments()

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.probe_ramper.trigger_single_sweep()


class TestRTBSetupFrag(ExpFragment):

    def build_fragment(self):
        # devices
        self.setattr_device("core")
        self.core: Core

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

        # There's probably a more elegant way of doing this
        self.rtb_device: RSDevice = self.get_device("vrs_scope")

        # Make an applet
        self.setattr_device("ccb")
        self.ccb: CCB

        ### This stuff should not be done in build fragment but probably somewhere later... needs to be done from the computer

    @host_only
    def host_setup(self):
        # self.rtb = RsInstrument("TCPIP::10.137.1.19::INSTR", id_query=True, reset=True)
        # Set the trigger to an external signal
        # Long timeout for visa
        self.rtb: RsInstrument = self.rtb_device.get_instrument()

        self.rtb.visa_timeout = 50000
        self.rtb.write_str_with_opc("TRIG:A:MODE NORM")
        self.rtb.write_str("TRIG:A:SOUR EXT")
        # Set the trigger to be the positive edge
        self.rtb.write_str("TRIG:A:TYPE EDGE")
        self.rtb.write_str("TRIG:A:EDGE:SLOP POS")
        # Set the trigger height to be 1 V
        self.rtb.write_str("TRIG:A:LEV5 1")
        # Ensure we are not in roll mode!
        self.rtb.write_float("TIM:ROLL:MTIM", self.acquisition_time.get() + 1.0)

        # Set the acquisition settings CH1 is the PMT signal
        self.rtb.write_float(
            "TIM:ACQT", self.acquisition_time.get()
        )  # Scope Acquisition time
        self.rtb.write_float("CHAN1:RANG", 5.0)  # Total Vertical range 5V (0.5V/div)
        self.rtb.write_float("CHAN1:OFFS", 0.0)  # Offset 0
        self.rtb.write_bool("CHAN1:STAT", True)  # Switch Channel 1 ON
        # Sample Data, we want the max of 20 MSa per segment
        self.rtb.write_float("ACQ:POIN", 1e6)
        # Setup a single shot

    @kernel
    def run_once(self) -> None:

        logger.warning("Begin the pulse")
        self.core.break_realtime()
        self.start_single()
        # Ok Delay for a bit of time to let the rest of the OPC commands finish
        delay(5.0)
        # self.core.wait_until_mu(now_mu())
        # self.core.wait_until_mu(now_mu())

        # Pulse the TTL for 10 ms
        # self.ttl.pulse(10e-3)
        self.ttl.on()
        # logger.warning("start the wait")
        delay(self.acquisition_time.get())
        # Get the data from the scope and save it in the results channel after we get to this part of the timeline
        self.ttl.off()
        self.core.wait_until_mu(now_mu())
        self.get_data_from_scope()
        # self.core.wait_until_mu(now_mu())

        # self.core.break_realtime()
        # logger.warning("I've gotten data!")

    # Does this need to be done on the PC?, how else would it manage to save the data
    # Also this is quite a large data set...
    # We can save this data on the scope internally and rerun the experiment
    @rpc
    def get_data_from_scope(self) -> None:
        # Save the data in ascii format and plot in the applet

        logger.warning("Query")
        # self.rtb.write_str("")
        # self.rtb.write_bool("CHAN2:STAT", True)  # Switch Channel 1 ON
        data = self.rtb.query_bin_or_ascii_float_list(
            "FORM ASC;:CHAN1:DATA:POIN MAX;:CHAN1:DATA?"
        )
        logger.warning(len(data))
        # data = self.rtb.query_bin_or_ascii_float_list("CHAN1:DATA:HEADer?")
        logger.warning("Data Here")

        self.scope_data.push(data)
        logger.warning("Pushed")
        self.set_dataset("scope_data", data, broadcast=True, archive=False)
        xs = np.linspace(0, self.acquisition_time.get(), len(data))
        self.set_dataset("frequency_sweep", xs, broadcast=True, archive=False)

        cmd = f"${{artiq_applet}}plot_xy scope_data --x frequency_sweep"
        self.ccb.issue("create_applet", "Scope Trace", cmd)

    @rpc
    def start_single(self) -> None:
        self.rtb.write_str("SING")


class TestDHOSetupFrag(ExpFragment):

    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core

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

        self.rigol: RigolDHO = self.get_device("vrs_scope")

        # Make an applet
        self.setattr_device("ccb")
        self.ccb: CCB

    @host_only
    def host_setup(self):
        # reset to default state
        self.rigol.reset()
        self.rigol.set_trigger_source("EDGE", "EXT")
        self.rigol.set_trigger_level("EDGE", 5)

        self.rigol.enable_roll(False)
        self.rigol.set_vertscale(1, 30e-3)
        self.rigol.set_acquisition_depth("10K")

        cmd = f"${{artiq_applet}}plot_xy scope_data --x frequency_sweep"
        self.ccb.issue("create_applet", "Scope Trace", cmd)

    @rpc
    def reset_scope(self):
        self.rigol.set_trigger_sweep("SING")
        self.rigol.set_timescale(self.acquisition_time.get() / 10)
        self.rigol.set_time_offset(self.acquisition_time.get() / 2)

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.reset_scope()

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        logger.warning("Begin the pulse")
        delay(1.0)
        self.ttl.on()
        delay(self.acquisition_time.get())
        self.ttl.off()
        delay(1.0)
        self.core.wait_until_mu(now_mu())
        self.get_data_from_scope()

    @rpc
    def get_data_from_scope(self):
        # need to parse the data from string to float array
        data = [float(x) for x in self.rigol.get_waveform().split(",")[:-1]]
        print(data)
        # self.scope_data.push(data)
        # self.scope_data.push(np.array(data, dtype=np.float32))

        self.scope_data.push([])

        xs = np.linspace(0, self.acquisition_time.get(), len(data))
        self.set_dataset("frequency_sweep", xs, broadcast=True, archive=False)


TestVRSProbeRamper = make_fragment_scan_exp(
    TestVRSProbeRamperFrag, max_rtio_underflow_retries=0
)

TestRTBSetup = make_fragment_scan_exp(TestRTBSetupFrag)

TestDHOSetup = make_fragment_scan_exp(TestDHOSetupFrag, max_rtio_underflow_retries=0)
