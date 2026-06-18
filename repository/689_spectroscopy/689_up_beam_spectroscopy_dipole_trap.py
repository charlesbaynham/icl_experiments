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
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)


class SpectroscopyWithKineticsUpBeamDipoleTrapFrag(
    RedSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    689nm up-beam spectroscopy from a (plain) dipole trap — Zeeman survey.

    **Minimal composition (2026-06-19, Charles's steer):** just put atoms in a
    dipole trap and pulse them. Load a single XODT (``LoadSingleXODTMixin``), set
    the compensation-coil field (``FieldBoostMixin`` via
    ``RedSpectroscopyDipoleTrapMixin``) and hold in-trap so the field settles
    (``bias_field_settling_time``, default 20 ms — well above the few-ms
    coil-settling time that nulled the earlier MOT-drop surveys), then release and
    fire the 689 nm up beam for ¹S₀→³P₁ spectroscopy. Read out the excited-state
    fraction with the normalised single-trap fast-kinetics readout
    (``NormalisedDipoleTrapFastKineticsMixin``).

    *No* evaporation / optical pumping / adiabatic cooling / painter / molasses
    ramp, and *no* 707/679 repump in the readout. The previous rebuild (d341bcc4)
    copied the *clock* (³P₀, metastable) composition — the full cooling chain plus
    a repumped readout — and imaged no atoms (RID 75198: empty FK frames even
    though a plain XODT loads a bright cloud, RID 75200). The 689 ³P₁ line does not
    need any of that: ³P₁ (~21 µs lifetime) decays back to ¹S₀ on its own, so the
    recovered frame fluoresces on 461 without repumping, and a plain trapped cloud
    is all the spectroscopy needs.

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

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()

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
