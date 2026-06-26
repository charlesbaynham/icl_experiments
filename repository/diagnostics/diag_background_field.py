r"""
Diagnostic 1 - Background magnetic field (drift check).

Measures the background B-field in the science chamber via the 689 nm
¹S₀->³P₁ line. It loads atoms the **standard** way every dipole-trap experiment
does - the single-XODT + fast-kinetics + normalised-repumped-readout stack that
the clock diagnostics load on (and which loads ~2.3e7 atoms) - and only swaps the
689 up-beam spectroscopy mixin in for the clock one. All the custom logic lives
at the *end* of the sequence, in ``RedSpectroscopyDipoleTrapMixin``'s hooks.

Sequence (loading/cooling/imaging all inherited; only the end is custom):

* load a single XODT (red MOT -> molasses + dipole ramp -> evaporation ->
  adiabatic cooling, painted), exactly as the clock diagnostics do;
* hold the atoms in the dipole trap and, **while still trapped**
  (``RedSpectroscopyDipoleTrapMixin.post_dipole_trap_hook``):
    - set the compensation field to the measurement value via ``field_boost()``
      (``x/y/z_coil_boost`` added on top of the nominal bias). That call drives
      the **3D-MOT gradient coil to ``spectroscopy_field_gradient`` = 0** (set by
      the single-XODT loader), i.e. the quadrupole field is **off** for the
      measurement - otherwise it would wreck the line;
    - **settle the field in-trap** (``bias_field_settling_time``, ~20 ms - coils
      take ms to settle);
    - **release the dipole trap** (``post_dipole_trap_hook_default`` turns the
      1064 light off);
* fire one short 689 up-beam spectroscopy pulse
  (``do_experiment_after_dipole_trap_hook`` -> ``do_red_spectroscopy``);
* fast-kinetics normalised readout (ground image -> 707 repump -> excited image
  -> background) gives ``excitation_fraction``.

This replaces the earlier composition (``LoadXXODTMixin`` +
``DoubleTrapImagingRepumpedNormalisedMixin``), which loaded/imaged **no atoms** on
this rig (RID 75432: flat camera background, atom number ~ 0). Fix (Charles,
2026-06-21): load the dipole trap the standard way and confine the custom work to
the end-of-sequence hook (already exactly what ``RedSpectroscopyDipoleTrapMixin``
does).

Geometry (up-beam k ∥ ẑ, linear polarisation; see CLAUDE.md): a field
component ∥ k (vertical z) drives σ⁺/σ⁻ that split symmetrically about a fixed
centre -> measure the *splitting*; a field ⊥ k (x/y) shifts the line -> measure
the *centroid shift*. This default run probes the resident background field at the
nominal compensation setting; per-coil sensitivity (and the full vector) is
obtained by adding ``x_coil_boost`` / ``y_coil_boost`` / ``z_coil_boost`` as a
second scan axis (available via the dashboard).

Working spectroscopy params baked in (validated, WS1 2026-06-15 survey):

* ``spectroscopy_pulse_time = 25 us`` - short pulse ~ the ~21 µs ³P₁ lifetime
  (long pulses are incoherent radiation-pressure push, not spectroscopy).
* ``spectroscopy_pulse_aom_amplitude = 0.3`` - amp 1.0 power-broadens, amp 0.1
  kills contrast; 0.3 is the validated compromise.
* ``em_gain_enabled = True``, ``em_gain = 30`` - the fast-kinetics readout needs
  EM gain (same value the clock diagnostics image cleanly with). EM gain is
  enabled **only** via the experiment's own flag, which reads (never writes) the
  ``DISABLE_EM_GAIN`` safety interlock and aborts safely if it forbids gain.

Default scan: ``spectroscopy_pulse_aom_detuning`` over ±600 kHz (AOM axis;
optical = 2×AOM via the double-pass injection AOM), 41 points, 2 repeats.
"""

import logging

from artiq.language import kernel
from ndscan.experiment import OnlineFit

from repository.diagnostics.dataset_fit_analysis import FitOutput
from repository.diagnostics.dataset_fit_analysis import make_dataset_fit_analysis
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (  # noqa: E501
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (  # noqa: E501
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


class BackgroundFieldDiagnosticFrag(
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
    """689 background-field diagnostic on the proven single-XODT + FK stack.

    Identical loading/cooling/imaging composition to
    ``ClockSpecFromSingleXODTFrag`` (which loads ~2.3e7 atoms), with the 689
    up-beam ``RedSpectroscopyDipoleTrapMixin`` swapped in for the clock-spec
    mixin. ``RedSpectroscopyDipoleTrapMixin`` already provides the end-of-sequence
    hooks: set the compensation field (with the 3D-MOT gradient off) and settle it
    in-trap, release the trap, then fire one 689 up-beam pulse. See module
    docstring.
    """

    def build_fragment(self):
        super().build_fragment()

        # EM gain for the fast-kinetics readout; enabled only via the experiment's
        # own flag (the EMGainMixin reads, never writes, DISABLE_EM_GAIN and aborts
        # safely if it forbids gain).
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

        # WEAK, SHORT pulse so the interrogation stays in the linear (low-excitation)
        # regime - off-resonant atoms barely driven, so a narrow line appears. On
        # this single-XODT + FK path the transition saturated badly: amp 0.3 gave
        # ~0.77 excitation flat at every detuning (RID 75453), and amp 0.1 barely
        # moved it (~0.70 flat, RID 75454) - i.e. deep saturation, insensitive to
        # amplitude, because the 25 us pulse exceeds the ~21 us 3P1 lifetime
        # (incoherent radiation-pressure push, not coherent spectroscopy). Cut the
        # pulse AREA decisively: shorter than a lifetime AND much weaker.
        self.override_param("spectroscopy_pulse_time", 12e-6)
        self.override_param("spectroscopy_pulse_aom_amplitude", 0.03)

    @kernel
    def set_postnarrowband_fields_hook(self):
        # Hook-collision fix. Both LoadSingleXODTMixin and
        # RedSpectroscopyDipoleTrapMixin override this hook (mixins must not share
        # a hook). With RedSpectroscopyDipoleTrapMixin first in the MRO, its
        # version (set_fields_default) wins and clobbers the single-XODT loader's
        # loading fields during the post-narrowband phase -> the dipole trap loads
        # NO atoms (observed RID 75432 / 75439). The single-XODT loader needs this
        # hook to do NOTHING (it sets its own loading fields); the working clock
        # diagnostics get that because their clock mixin doesn't touch this hook.
        # Restore the loader's no-op here. The measurement compensation field is
        # still applied in-trap later, in post_dipole_trap_hook -> field_boost().
        pass

    @kernel
    def DMA_initialization_hook(self):
        # Mirror ClockSpecFromSingleXODTFrag: arm DMA for every loading/cooling
        # phase in the stack (red MOT, dipole trap, XODT-MOT load, evap with field
        # ramp, adiabatic cooling, painter).
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
        # Line-centre fit on the AOM detuning axis (FK single-trap excitation).
        # OnlineFit draws the live curve; make_dataset_fit_analysis additionally
        # writes the fitted line centre (and its error) into result datasets.
        return [
            OnlineFit(
                "lorentzian",
                data={
                    "x": self.spectroscopy_pulse_aom_detuning,
                    "y": self.excitation_fraction,
                },
            )
        ] + make_dataset_fit_analysis(
            fit_type="lorentzian",
            x=self.spectroscopy_pulse_aom_detuning,
            y=self.excitation_fraction_forward,
            outputs=[
                FitOutput(
                    "line_centre_aom",
                    "Fitted 1S0->3P1 line centre on the AOM axis",
                    fit_key="x0",
                    unit="kHz",
                ),
                FitOutput(
                    "line_fwhm",
                    "Fitted Lorentzian FWHM",
                    fit_key="fwhm",
                    unit="kHz",
                ),
            ],
        )


# Default-runnable detuning scan across the 689 1S0->3P1 line on the AOM axis.
# +-600 kHz AOM (= +-1.2 MHz optical, double-pass), 41 points, 2 repeats.
BackgroundFieldDiagnostic = make_default_scan_exp(
    BackgroundFieldDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="spectroscopy_pulse_aom_detuning",
            start=-600e3,
            stop=600e3,
            num_points=41,
        ),
    ],
    default_num_repeats=2,
)
