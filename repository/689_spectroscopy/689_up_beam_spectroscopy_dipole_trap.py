import logging

from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)


class SpectroscopyWithKineticsUpBeamDipoleTrapFrag(
    RedSpectroscopyDipoleTrapMixin,
    TripleImageDipoleTrapFastKineticsMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
):
    """
    689nm up-beam spectroscopy from a dipole trap (Zeeman survey)

    Loads a single XODT, sets the compensation-coil field (FieldBoostMixin), holds
    in-trap so the field FULLY settles (``bias_field_settling_time``, default 20 ms,
    well above the few-ms coil-settling time that nulled earlier MOT-drop surveys),
    then releases and fires the 689 nm up beam for ¹S₀->³P₁ spectroscopy. Reads out
    the excited-state fraction with the validated fast-kinetics triple imaging
    (frame0 fired within the ~21 µs ³P₁ lifetime to catch the ground-state
    depletion while excited atoms are still dark; frame1 long after = recovered
    total; frame2 = background).

    This is the modern, dipole-trap replacement for the revived MOT-drop
    ``SpectroscopyWithKineticsUpBeam`` experiment. Colder, in-trap-settled atoms
    give a narrower, Doppler-limited line, and the in-trap field hold removes the
    coil-settling artefact, so the per-coil Zeeman sensitivity (x/y centroid shift,
    z splitting) can be measured cleanly.

    Scan axes for the Zeeman survey: ``spectroscopy_pulse_aom_detuning`` against the
    per-axis compensation boost ``x_coil_boost`` / ``y_coil_boost`` /
    ``z_coil_boost`` (FieldBoostMixin). Pulse time/amplitude
    (``spectroscopy_pulse_time`` / ``spectroscopy_pulse_aom_amplitude``) tune the
    line width.

    Mixin roles:

    * ``RedSpectroscopyDipoleTrapMixin`` - configures the up beam (defaults
      ``spectroscopy_beam`` to ``up``), sets the boosted field in
      ``post_dipole_trap_hook``, holds for ``bias_field_settling_time`` to settle
      the coils, then fires the pulse in ``do_experiment_after_dipole_trap_hook``.
    * ``TripleImageDipoleTrapFastKineticsMixin`` - validated excited-state
      fast-kinetics readout with the dipole-trap ROI / FK geometry.
    * ``EMGainMixin`` - enables EM gain only via ``em_gain_enabled`` (reads, never
      writes, the ``DISABLE_EM_GAIN`` safety interlock and aborts safely if it
      forbids gain).
    * ``LoadSingleXODTMixin`` - red MOT -> single XODT loading and the matching
      DMA initialisation.
    """

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
