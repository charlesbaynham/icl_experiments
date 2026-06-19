import logging

from artiq.language import kernel
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODTMixin,
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
    def set_postnarrowband_fields_hook(self):
        # Do NOT touch the fields here. RedSpectroscopyDipoleTrapMixin's version
        # calls set_fields_default() -> set_mot_gradient(0), which zeroes the MOT
        # quadrupole gradient right after the narrowband red MOT and BEFORE the
        # XODT transfer (MOTInSingleXODT has no field ramp of its own and relies
        # on the gradient left in place) -> the trap loads no atoms. Suppress it,
        # exactly as LoadSingleXODTWithPainterMixin does. The compensation boost is
        # still applied later in post_dipole_trap_hook via field_boost().
        pass

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


class SpectroscopyUpBeamDipoleTrapImagedFrag(
    RedSpectroscopyDipoleTrapMixin,
    BGCorrectedAndorImageSingleXODTMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    689nm up-beam spectroscopy from a dipole trap, read out by SIMPLE imaging.

    Same physics as ``SpectroscopyWithKineticsUpBeamDipoleTrapFrag`` (load a plain
    XODT, set the compensation field, settle, drop, fire the 689 up-beam pulse) but
    reads out with the **proven background-corrected single-image readout**
    (``BGCorrectedAndorImageSingleXODTMixin`` — the same readout that cleanly images
    the trapped cloud, RID 75200) instead of the fast-kinetics readout.

    *Why:* on the rig the fast-kinetics readout images NO atoms even though the XODT
    loads a bright cloud (RID 75198, RID 75201): the FK strip/ROI does not capture
    the cloud (an FK-geometry / Andor-grabber axis-flip issue, present in the
    original over-built version too). The single-image readout's ROI *does* capture
    it. The 689 spectroscopy signal is then the **atom-number / fluorescence DIP**
    on resonance: the on-resonance 689 pulse scatters/heats atoms out of the trap,
    so ``andor_sum_bg_corrected`` dips at the line centre.

    Scan axes: ``spectroscopy_pulse_aom_detuning`` against ``x/y/z_coil_boost``.
    X/Y shift the line centroid (B ⊥ k); Z splits σ⁺/σ⁻ about a fixed centre
    (B ∥ k = ẑ).
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def set_postnarrowband_fields_hook(self):
        # See SpectroscopyWithKineticsUpBeamDipoleTrapFrag: suppress the
        # RedSpectroscopyDipoleTrapMixin default that zeroes the MOT gradient
        # before the XODT transfer (which otherwise loads no atoms).
        pass

    def get_default_analyses(self):
        return [
            OnlineFit(
                "lorentzian",
                data={
                    "x": self.spectroscopy_pulse_aom_detuning,
                    "y": self.andor_sum_bg_corrected,
                },
            )
        ]


SpectroscopyUpBeamDipoleTrapImaged = make_fragment_scan_exp(
    SpectroscopyUpBeamDipoleTrapImagedFrag
)
