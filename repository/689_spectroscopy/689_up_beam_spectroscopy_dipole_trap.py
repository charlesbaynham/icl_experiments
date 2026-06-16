import logging

from artiq.language import kernel
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class SpectroscopyWithKineticsUpBeamDipoleTrapFrag(
    RedSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    DipoleTrapWithExperimentBase,
):
    """
    689nm up-beam spectroscopy from a dipole trap (Zeeman survey)

    Load a single XODT, molasses-cool + evaporate + optically pump + adiabatically
    cool into a tight, cold cloud, set the compensation-coil field
    (``FieldBoostMixin``) and hold in-trap so the field FULLY settles
    (``bias_field_settling_time``, default 20 ms, well above the few-ms
    coil-settling time that nulled earlier MOT-drop surveys), then release and fire
    the 689 nm up beam for ¹S₀->³P₁ spectroscopy. Read out the excited-state
    fraction with the normalised single-trap fast-kinetics readout, **repumping
    (707/679) after the ground-state frame** so the excited population is recycled
    and fluoresces (``NormalisedFastKineticsRepumpedMixin``).

    This composition mirrors the proven single-XODT spectroscopy experiment
    ``ClockSpecFromSingleXODTFrag``
    (``repository/clock_spectroscopy/clock_spectroscopy_from_XODT.py``), swapping
    the clock spectroscopy for the red up-beam spectroscopy
    (``RedSpectroscopyDipoleTrapMixin``).

    *Rationale for the rebuild (2026-06-16):* the first version composed bare
    ``LoadSingleXODTMixin`` + the non-repumped ``TripleImageDipoleTrapFastKinetics``
    readout. It ran end-to-end on hardware (RID 74677) but imaged NO atoms: with no
    cooling chain the cloud was not tight/localised, and with no repump the excited
    frame had no recycled fluorescence. Root-caused via the control RID 74680 (the
    same XODT loading images a clean ~951k-count cloud) and the raw image RID 74679
    (no cloud anywhere in the FK frame). This rebuild adds the cooling chain + the
    repumped normalised readout to fix it. **Pending rig validation (next
    session).**

    Scan axes for the Zeeman survey: ``spectroscopy_pulse_aom_detuning`` against the
    per-axis compensation boost ``x_coil_boost`` / ``y_coil_boost`` /
    ``z_coil_boost`` (``FieldBoostMixin``). X/Y shift the line centroid (B ⊥ k);
    Z splits σ⁺/σ⁻ symmetrically about a fixed centre (B ∥ k = ẑ).
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_painter_on()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_loading()

    def get_default_analyses(self):
        return [
            OnlineFit(
                "lorentzian",
                data={
                    "x": self.spectroscopy_pulse_aom_detuning,
                    "y": self.excitation_fraction,
                },
            )
        ]


SpectroscopyWithKineticsUpBeamDipoleTrap = make_fragment_scan_exp(
    SpectroscopyWithKineticsUpBeamDipoleTrapFrag
)
