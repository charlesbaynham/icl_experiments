r"""
Diagnostic 1 - Background magnetic field (drift check).

Measures the background B-field in the science chamber via the 689 nm
¹S₀->³P₁ line, reusing the **proven** repumped XXODT spectroscopy readout
(the same composition as ``RedSpectroscopyFromXXODTFrag``, "689 spectroscopy from
dropped XXODT"). That path loads an XXODT, optically pumps / sets the field,
fires the 689 up beam, then images the ground state, repumps (707) and images
the excited state, and images once more for background - giving a
*repumped, normalised* excitation readout (``excitation_fraction_forward``).

This deliberately does **not** use WS1's fast-kinetics dipole-trap composition
(``TripleImageDipoleTrapFastKineticsMixin`` + ``LoadSingleXODTMixin``), which was
found to image *nothing* without the 707 repump + cooling chain. The fragment is
composed directly from the proven mixins (rather than importing
``RedSpectroscopyFromXXODTFrag``) because that experiment file is named with a
leading digit and is not an importable module.

Default-runnable: submitting with ``arguments={}`` scans the up-beam AOM detuning
across the ¹S₀->³P₁ line at the nominal (zero-boost) compensation field, with the
validated working pulse / EM-gain parameters baked in. The baked-in Lorentzian
``OnlineFit`` returns the line centre on the AOM axis; the field is read out from
that centre relative to the known nominal line position (see the analysis
notebook).

Geometry (up-beam k ∥ ẑ, linear polarisation; see CLAUDE.md): a field
component ∥ k (vertical z) drives σ⁺/σ⁻ that split symmetrically about a fixed
centre -> measure the *splitting*; a field ⊥ k (x/y) shifts the line -> measure
the *centroid shift*. This default run probes the resident background field at
the nominal compensation setting; per-coil sensitivity (and the full vector) is
obtained by adding ``x_coil_boost`` / ``y_coil_boost`` / ``z_coil_boost`` as a
second scan axis (still available via the dashboard).

Working parameters baked in (validated, WS1 2026-06-15 survey):

* ``em_gain_enabled = True``, ``em_gain = 50`` - needed for the weak short-pulse
  signal. EM gain is enabled **only** via the experiment's own
  ``em_gain_enabled`` flag, which reads (never writes) the ``DISABLE_EM_GAIN``
  safety interlock and aborts safely if it forbids gain.
* ``spectroscopy_pulse_time = 25 us`` - short pulse ≲ the ~21 µs ³P₁ lifetime
  (long pulses are incoherent radiation-pressure push, not spectroscopy).
* ``spectroscopy_pulse_aom_amplitude = 0.3`` - amp 1.0 power-broadens the line,
  amp 0.1 kills contrast; 0.3 is the validated compromise.

Default scan: ``spectroscopy_pulse_aom_detuning`` over ±600 kHz (AOM axis;
optical = 2×AOM via the double-pass injection AOM), 41 points, 2 repeats.
"""

import logging

from ndscan.experiment import OnlineFit

from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (  # noqa: E501
    DoubleTrapImagingRepumpedNormalisedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadXXODTMixin

logger = logging.getLogger(__name__)


class BackgroundFieldDiagnosticFrag(
    RedSpectroscopyDipoleTrapMixin,
    DoubleTrapImagingRepumpedNormalisedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadXXODTMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """689 background-field diagnostic.

    Same mixin composition as the proven ``RedSpectroscopyFromXXODTFrag`` (689
    spectroscopy from a dropped XXODT, with 707-repumped normalised imaging):
    loads an XXODT, optically pumps / sets the compensation field
    (FieldBoostMixin, with the in-trap ``bias_field_settling_time`` hold that
    removes the coil-settling artefact), releases and fires the 689 up beam, then
    images ground -> repump -> excited -> background. Defaults tuned for a
    default-runnable background-field check. See module docstring.
    """

    def build_fragment(self):
        super().build_fragment()

        # Validated working readout. EM gain enabled only via the experiment's own
        # flag; the DISABLE_EM_GAIN interlock is never touched (the EMGainMixin
        # reads it and aborts safely if it forbids gain).
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 50.0)

        # Short pulse <~ the ~21 us 3P1 lifetime; moderate amplitude for a
        # resolvable, not-power-broadened line.
        self.override_param("spectroscopy_pulse_time", 25e-6)
        self.override_param("spectroscopy_pulse_aom_amplitude", 0.3)

    def get_default_analyses(self):
        # Line-centre fit on the AOM detuning axis (excited-fraction peak).
        return [
            OnlineFit(
                "lorentzian",
                data={
                    "x": self.spectroscopy_pulse_aom_detuning,
                    "y": self.excitation_fraction_forward,
                },
            )
        ]


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
