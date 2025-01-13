import logging

from artiq.experiment import kernel
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
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
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
        self.dipole_trap_evaporation_hook_default()  # FIXME

        # Blast the atoms with the stark pulse during the evap stage
        self.stark_shifter.do_stark_pulse()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class DoubleXODTAbsFrag(
    AbsorptionDoubleDipoleTrapMixin,
    XODTSingleMolassesMixin,
):
    """
    Measure a double XODT with aborption imaging

    Load a red MOT, then implement a single "molasses" stage which is
    actually another MOT with a field bias to move it to the bottom trap.
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureXXODT = make_fragment_scan_exp(DoubleXODTFrag)
MeasureXXODTAbs = make_fragment_scan_exp(DoubleXODTAbsFrag)
