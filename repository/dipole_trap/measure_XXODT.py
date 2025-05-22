import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadXXODTMixin
from repository.lib.fragments.stark_shifter import StarkShifter

logger = logging.getLogger(__name__)


class MeasureXXODTFrag(
    DoubleTrapImagingBGSubtracted,
    FLIRBlueMOTMeasurementMixin,
    LoadXXODTMixin,
    EMGain,
):
    """
    Measure a double XODT

    Load a red MOT on the top XODT, drop the bias field to centre the MOT on the
    second XODT then turn the light back on.
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class StarkBlastXXODTFrag(
    DoubleTrapImagingBGSubtracted,
    FLIRBlueMOTMeasurementMixin,
    LoadXXODTMixin,
    EMGain,
):
    """
    Blast an XXODT with the Stark shifter

    In the "evaporation" stage, the 689 nm Stark beam is pulsed on to destroy atoms
    (for alignment of the beam onto the XODT). Note: this will only work the
    0th order of the 689 delivery AOM is coupled to the chamber - otherwise the
    beam will be ~ 100 MHz from resonance.
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
            default=10e-3,
            description="Duration of the Stark shifter pulse to destroy atoms in the XXODT",
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


class MeasureXXODTAbsorptionFrag(
    AbsorptionDoubleDipoleTrapMixin,
    LoadXXODTMixin,
):
    """
    Measure a double XODT with absorption imaging
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureXXODT = make_fragment_scan_exp(MeasureXXODTFrag, max_rtio_underflow_retries=0)
StarkBlastXXODT = make_fragment_scan_exp(
    StarkBlastXXODTFrag, max_rtio_underflow_retries=0
)
MeasureXXODTAbsorption = make_fragment_scan_exp(
    MeasureXXODTAbsorptionFrag, max_rtio_underflow_retries=0
)
