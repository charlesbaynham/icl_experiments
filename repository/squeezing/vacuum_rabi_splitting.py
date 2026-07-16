import logging

import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import rpc
from artiq.master.worker_impl import CCB
from ndscan.experiment import OpaqueChannel
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.constants import VRS_SWEEP_ATTENUATION
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImageMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
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

    This sequence traps the atoms from a narrowband red mot and does a vacuum Rabi
    splitting measurement. This includes preparing a scope to readout from the PMT
    and triggering it while sweeping the amplitude modulator on the 689 probe beam.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks)

        * :meth:`~do_experiment_after_red_mot_hook`
        * :meth:`~host_functions_after_experiment_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        # devices
        self.setattr_device("core")
        self.core: Core

        # Probe sweep DDS
        self.dds: AD9910 = self.get_device("urukul9910_squeezing_probe")
        self.setattr_device

        # Init of the Probe sweep DDS without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulSweeper",
            GlitchFreeUrukulDefaultAttenuation,
            "urukul9910_squeezing_probe",
            VRS_SWEEP_ATTENUATION,
        )

        # Scope trigger ttl
        self.ttl = self.get_device("ttl_vrs_scope_trigger")
        self.ttl: TTLOut

        # RS Scope for the VRS measurement
        # self.rtb_device: RSDevice = self.get_device("vrs_scope")

        # Make an applet
        self.setattr_device("ccb")
        self.ccb: CCB

        # Params
        self.setattr_param(
            "acquisition_time",
            FloatParam,
            "Scope Acquisition Time",
            default=0.3,
            unit="ms",
            min=0.0,
        )
        self.acquisition_time: FloatParamHandle

        self.setattr_param(
            "save_trace",
            BoolParam,
            "Save the trace",
            default=True,
        )
        self.save_trace: BoolParamHandle

        # Fragments
        self.setattr_fragment(
            "probe_ramper", VRS_Probe_Ramper, "urukul9910_squeezing_probe"
        )
        self.probe_ramper: VRS_Probe_Ramper

        # Variable
        self.setattr_result("scope_data", OpaqueChannel)
        self.scope_data: ResultChannel

        # Bind the sweep time to be the acquisition time of the scope
        self.probe_ramper.bind_param("sweep_time", self.acquisition_time)

        # Afterall, why shouldn't I follow the narrowband mot epxerimetn
        self.override_param("delay_after_experiment", 0)
        self.override_param("spectroscopy_field_gradient", 0)

        # Invariants
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dds")

    @host_only
    def host_setup(self):
        super().host_setup()

        # and write a bunch of stuff to the scope
        # self.rtb = RsInstrument(
        #     get_configuration_from_db("VRS_scope_address"), id_query=True, reset=True
        # )
        # self.rtb: RsInstrument = self.rtb_device.get_instrument()

        # Set a long Long timeout for visa
        # self.rtb.visa_timeout = 100000
        # Set the trigger to an external signal
        # self.rtb.write_str_with_opc("TRIG:A:MODE NORM")
        # self.rtb.write_str("TRIG:A:SOUR EXT")
        # Set the trigger to be the positive edge
        # self.rtb.write_str("TRIG:A:TYPE EDGE")
        # self.rtb.write_str("TRIG:A:EDGE:SLOP POS")
        # Set the trigger height to be 1 V
        # self.rtb.write_str("TRIG:A:LEV5 1")

        # Set the acquisition settings CH1 is the PMT signal
        # self.rtb.write_float(
        # "TIM:ACQT", self.acquisition_time.get()
        # )  # Scope Acquisition time
        # Set the trigger position to be at the start of the scope
        # self.rtb.write_float("TIM:POS", self.acquisition_time.get() / 2)

        # self.rtb.write_float("CHAN1:RANG", 0.2)  # Total Vertical range 5V (0.5V/div)
        # self.rtb.write_float("CHAN1:OFFS", -0.05)  # Offset 0
        # self.rtb.write_bool("CHAN1:STAT", True)  # Switch Channel 1 ON
        # Sample Data, we want the max of 20 MSa per segment
        # self.rtb.write_float("ACQ:POIN", 1e6)

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        delay(200e-3)
        self.dds.sw.set_o(True)
        self.dds.set(self.probe_ramper.min_f.get())
        # Make sure it starts in the off position
        self.ttl.off()
        self.core.break_realtime()

    @kernel
    def do_experiment_after_red_mot_hook(self):
        # self.core.break_realtime()
        # Switch the ttl on without advancing the timeline
        self.ttl.on()
        self.probe_ramper.trigger_single_sweep()
        self.ttl.off()

    @kernel
    def host_functions_after_experiment_hook(self):
        self.host_functions_after_experiment_hook_default()

        # Save the data!
        # if self.save_trace.get() is True:
        # self.get_data_from_scope()
        # else:
        # pass

    @rpc
    def get_data_from_scope(self) -> None:
        # Save the data in ascii format and save
        # logger.warning("Query")
        data = self.rtb.query_bin_or_ascii_float_list(
            "FORM ASC;:CHAN1:DATA:POIN MAX;:CHAN1:DATA?"
        )
        logger.warning(len(data))
        self.scope_data.push(data)
        self.set_dataset("scope_data", data, broadcast=True, archive=False)

        fs = np.linspace(
            self.probe_ramper.min_f.get(), self.probe_ramper.max_f.get(), len(data)
        )
        self.set_dataset("frequency_sweep", fs, broadcast=True, archive=False)

        cmd = f"${{artiq_applet}}plot_xy scope_data --x frequency_sweep"
        self.ccb.issue("create_applet", "Scope Trace", cmd)


SingleVRSSweep = make_fragment_scan_exp(
    SingleVRSSweepFrag, max_rtio_underflow_retries=0
)
