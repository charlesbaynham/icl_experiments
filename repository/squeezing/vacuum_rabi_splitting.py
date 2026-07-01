import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.urukul import CPLD
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from ndscan.experiment import OpaqueChannel
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from RsInstrument import RsInstrument

from repository.lib.constants import VRS_SCOPE_ADDRESS
from repository.lib.constants import VRS_URUKUL_CHANNEL
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImageMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.vrs_probe_ramper import VRS_Probe_Ramper

logger = logging.getLogger(__name__)

from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)


class SingleVRSSweepFrag(
    FLIRMeasurementMixin,
    SingleAndorImageMixin,
    ConstantBeamsMixin,
    RedMOTWithExperimentBase,
):
    """
    Single sided RF sweep on the 689 VRS AM
    """

    def build_fragment(self):
        super().build_fragment()

        # devices
        self.setattr_device("core")
        self.core: Core

        # Probe sweep DDS
        self.dds: AD9910 = self.get_device(VRS_URUKUL_CHANNEL)
        self.setattr_device

        # Scope trigger ttl
        self.ttl = self.get_device("ttl_vrs_scope_trigger")
        self.ttl: TTLOut

        # Params
        self.setattr_param(
            "attenuation",
            IntParam,
            "DDS attenuation",
            min=0,
            max=30,
            default=30,
            unit="dB",
        )
        self.attenuation: IntParamHandle

        # TODO: Change this to automatically match the sweep time of the dds
        self.setattr_param(
            "acquisition_time",
            FloatParam,
            "Scope Acquisition Time",
            default=0.3,
            unit="ms",
            min=0.0,
        )
        self.acquisition_time: FloatParamHandle

        # Fragments
        self.setattr_fragment("probe_ramper", VRS_Probe_Ramper, VRS_URUKUL_CHANNEL)
        self.probe_ramper: VRS_Probe_Ramper

        # Variable
        self.setattr_result("scope_data", OpaqueChannel)
        self.scope_data: ResultChannel

        # Bind the sweep time to be the acquisition time of the scope
        self.probe_ramper.bind_param("sweep_time", self.acquisition_time)

        # Invariants
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dds")

    @host_only
    def host_setup(self):
        super().host_setup()

        # initiate the cpld for the VRS urukul channel
        self.cpld: CPLD = self.dds.cpld

        # and write a bunch of stuff to the scope
        self.rtb = RsInstrument(VRS_SCOPE_ADDRESS, True, True)
        # Set a long Long timeout for visa
        self.rtb.visa_timeout = 50000
        # Set the trigger to an external signal
        self.rtb.write_str_with_opc("TRIG:A:MODE NORM")
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
        self.rtb.write_float("ACQ:POIN", 1e6)

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        delay(200e-3)
        self.cpld.init()
        self.dds.init()
        delay(1e-3)
        self.dds.sw.set_o(True)
        self.dds.set_att(float(self.attenuation.get()))
        self.core.break_realtime()

    @kernel
    def before_start_hook(self):
        # Setup a single shot
        self.start_single()
        # Ok Delay for a bit of time to let the rest of the OPC commands finish
        delay(1.5)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.core.break_realtime()
        # Switch the ttl on without advancing the timeline
        self.ttl.on()
        # I think add a bit of delay to advance the timeline to prevent clashes, but also it'd be nice if it was simultaneous...
        # TODO: Check if I need this delay
        delay_mu(100)
        self.probe_ramper.trigger_single_sweep()
        # Get the data from the scope and save it in the results channel after we get to this part of the timeline
        self.core.wait_until_mu(now_mu())
        self.get_data_from_scope()
        self.ttl.off()
        # self.core.break_realtime()
        # delay_mu(4)
        # logger.warning("I've gotten data!")

    # Does this need to be done on the PC?, how else would it manage to save the data
    # Also this is quite a large data set...
    # We can save this data on the scope internally and rerun the experiment
    @rpc
    def get_data_from_scope(self) -> None:
        # Save the data in ascii format and save

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

    @rpc
    def start_single(self) -> None:
        self.rtb.write_str("SING")


SingleVRSSweep = make_fragment_scan_exp(SingleVRSSweepFrag)
