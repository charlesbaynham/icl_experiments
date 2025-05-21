import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
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
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)
from repository.lib.fragments.stark_shifter import StarkShifter

logger = logging.getLogger(__name__)

EXPOSE_MOLASSES_1_PARAMS = False
EXPOSE_MOLASSES_2_PARAMS = True


class DoubleXODTFrag(
    DoubleTrapImagingBGSubtracted,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesMixin,
    EMGain,
):
    """
    Measure a double XODT

    Load a red MOT, then implement a single "molasses" stage which is
    actually another MOT with a field bias to move it to the bottom trap

    In the "evaporation" stage, the 689 nm Stark beam is pulsed on to destroy atoms
    (for alignment of the beam onto the XODT). Note: this will only work the
    0th order of the 689 delivery AOM is coupled to the chamber - otherwise the
    beam will be ~ 100 MHz from resonance. The default 689 pulse time is 0.01us
    to allow unadulterated imaging of the atoms in the XXODT as default.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("stark_shifter", StarkShifter)
        self.stark_shifter: StarkShifter

        # Keep old naming for backwards compatibility
        self.setattr_param_rebind(
            "stark_689_destroy_atoms_in_XODT_duration",
            self.stark_shifter,
            "stark_pulse_duration",
        )

    @kernel
    def dipole_trap_evaporation_hook(self):
        # Turns off red MOT beams - helpful!
        self.dipole_trap_evaporation_hook_default()

        # Blast the atoms with the stark pulse during the evap stage
        self.stark_shifter.do_stark_pulse()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class DoubleXODTAbsFrag(
    AbsorptionDoubleDipoleTrapMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
):
    """
    Measure a double XODT with aborption imaging

    Load a red MOT, then implement a single "molasses" stage which is
    actually another MOT with a field bias to move it to the bottom trap.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

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
MeasureXXODTAbs = make_fragment_scan_exp(DoubleXODTAbsFrag)
# Experiments using the XODTDoubleMolassesMixin. If we don't use these in a while, we should just delete them
# MeasureDoubleDipoleTrap = make_fragment_scan_exp(MeasureDoubleDipoleTrapFrag)
# MeasureDoubleDipoleTrapWithFieldRamp = make_fragment_scan_exp(
#     MeasureDoubleDipoleTrapWithFieldRampFrag
# )
# NormalizedDoubleDipoleTrap = make_fragment_scan_exp(NormalizedDoubleDipoleTrapFrag)
