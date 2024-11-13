import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.urukul_init import make_urukul_init
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTDoubleMolassesMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTDoubleMolassesPlusFieldRampMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
)

logger = logging.getLogger(__name__)

EXPOSE_MOLASSES_1_PARAMS = False
EXPOSE_MOLASSES_2_PARAMS = True

STARK_689_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["stark_shifter_689"]


class DoubleXODTFrag(
    DoubleTrapImagingBGSubtracted,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesMixin,
):
    """
    Measure a double XODT

    Load a red MOT, then implement a single "molasses" stage which is
    actually another MOT with a field bias to move it to the bottom trap

    In the "evaporation" stage, switch on the 689 nm beam to destroy atoms
    (for alignment of the beam onto the XODT). Note: this will only work the
    0th order of the 689 delivery AOM is coupled to the chamber - otherwise the
    beam will be ~ 100 MHz from resonance
    """

    def build_fragment(self):
        super().build_fragment()

        self.stark_689_dds: AD9912 = self.get_device(STARK_689_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.stark_689_initiator = self.setattr_fragment(
            "stark_689_initiator", make_urukul_init([STARK_689_BEAM_INFO.urukul_device])
        )

        self.setattr_param(
            "stark_689_destroy_atoms_in_XODT_duration",
            FloatParam,
            "Time allowed to destroy atoms in XODT using 689 Stark beam",
            default=0.01e-3,
            unit="ms",
        )
        self.stark_689_destroy_atoms_in_XODT_duration: FloatParamHandle

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_xodt_molasses()
        self.stark_689_dds.set_att(STARK_689_BEAM_INFO.attenuation)
        self.stark_689_dds.set(frequency=STARK_689_BEAM_INFO.frequency)
        self.stark_689_dds.sw.off()
        self.stark_689_dds.cfg_sw(False)

    @kernel
    def dipole_trap_evaporation_hook(self):
        self.stark_689_dds.sw.on()
        delay(self.stark_689_destroy_atoms_in_XODT_duration.get())
        self.stark_689_dds.sw.off()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class _MeasureDipoleTrapBase(
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    XODTDoubleMolassesMixin,
):
    """
    Load a dipole trap, do 689 nm molasses, hold, and take BG subtracted image
    """

    def build_fragment(self):
        super().build_fragment()

        # Expose the molasses ramp parameters if desired
        if EXPOSE_MOLASSES_1_PARAMS:
            names = [
                n
                for n in self.molasses_xodt_1._free_params.keys()
                if "suservo" not in n
            ]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_1_{name}", self.molasses_xodt_1, original_name=name
                )
        if EXPOSE_MOLASSES_2_PARAMS:
            names = [n for n in self.molasses_xodt_2._free_params.keys()]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_2_{name}", self.molasses_xodt_2, original_name=name
                )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureDoubleDipoleTrapFrag(
    DoubleTrapImagingBGSubtracted, _MeasureDipoleTrapBase
):
    pass


class MeasureDoubleDipoleTrapWithFieldRampFrag(
    XODTDoubleMolassesPlusFieldRampMixin, MeasureDoubleDipoleTrapFrag
):
    pass


class NormalizedDoubleDipoleTrapFrag(
    DoubleTrapImagingNormalised, _MeasureDipoleTrapBase
):
    pass


MeasureXXODT = make_fragment_scan_exp(DoubleXODTFrag)
# Experiments using the XODTDoubleMolassesMixin. If we don't use these in a while, we should just delete them
# MeasureDoubleDipoleTrap = make_fragment_scan_exp(MeasureDoubleDipoleTrapFrag)
# MeasureDoubleDipoleTrapWithFieldRamp = make_fragment_scan_exp(
#     MeasureDoubleDipoleTrapWithFieldRampFrag
# )
# NormalizedDoubleDipoleTrap = make_fragment_scan_exp(NormalizedDoubleDipoleTrapFrag)
