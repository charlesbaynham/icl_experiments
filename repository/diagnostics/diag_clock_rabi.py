r"""
Diagnostics 2 & 3 - Clock Rabi frequency (down beam / up beam).

Two separate default-runnable diagnostics that measure the clock Rabi frequency
on each clock beam by velocity-selecting ("slicing"/shelving) the cloud and then
scanning the clock spectroscopy pulse time, fitting the resulting Rabi flop.

Both wrap the existing clock-spectroscopy machinery
(``ClockSpecPulseRatioFrag`` = ``CompensatedClockSpecMixin`` + the XODT /
fast-kinetics stack). The clock-shelving velocity selection is intrinsic to that
fragment (``CompensatedClockSpecMixin.clock_shelving`` runs before every clock
pulse, duration ``T_sel = spectroscopy_pulse_time * pulse_ratio``), so the flop
is measured on a sliced (narrow-velocity) sub-ensemble.

Diagnosed quantity: the Rabi frequency, via the ``decaying_sinusoid`` ``OnlineFit``
over ``spectroscopy_pulse_time`` (``pi_time = t_max_transfer``; Rabi frequency
= 1 / (2 * pi_time)). ``decaying_sinusoid`` (with ``t_dead = 0``) is the
excitation-fraction-from-zero Rabi fit also used by the WS1 689 spectroscopy.

On resonance: ``extra_clock_detuning = 0`` (default) keeps the OPLL on the clock
line. The clock delivery setpoint is auto-scaled from the reference pi-pulse, so
no separate amplitude knob is needed - the flop frequency is whatever the beam
currently delivers at the reference setpoint, which is exactly what the
diagnostic reports.

Beam selection (``CompensatedClockSpecMixin.use_down_beam``):

* down beam -> ``use_down_beam = True``  (diagnostic 2)
* up beam   -> ``use_down_beam = False`` (diagnostic 3, the param default)

Default pulse-time scans span >=5 expected pi-times (40 points) so several flop
cycles are captured. They start at a small nonzero pulse time (5 us), not 0: the
clock delivery setpoint is auto-scaled as ``V = V_ref * (T_ref / T_clock)^2``,
which divides by the pulse time, so a t=0 point raises ZeroDivisionError on the
core device (observed RID 74681).

* up beam   (pi ~55 us): 5 -> 300 us, 40 points
* down beam (pi ~68 us): 5 -> 400 us, 40 points

EM gain is enabled by default in the experiment (``em_gain_enabled = True``,
``em_gain = 30``) so a default ``arguments={}`` run is self-sufficient. Gain is
enabled only via the experiment's own flag; the ``DISABLE_EM_GAIN`` safety
interlock is never touched.
"""

import logging

from ndscan.experiment import OnlineFit

from repository.clock_spectroscopy.clock_spectroscopy_pulse_ratio import (
    ClockSpecPulseRatioFrag,
)
from repository.diagnostics.dataset_fit_analysis import FitOutput
from repository.diagnostics.dataset_fit_analysis import make_dataset_fit_analysis
from repository.lib import constants
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp

logger = logging.getLogger(__name__)


def _rabi_frequency_from_pi_time(fit_results, fit_errs):
    """Rabi frequency f = 1 / (2 * t_pi) from the fitted pi-time, with its error.

    A full Rabi flop has excitation ~ sin^2(pi * t / (2 * t_pi)), so the Rabi
    frequency (full oscillation rate) is 1 / (2 * t_pi). The error propagates as
    df = dt_pi / (2 * t_pi^2).
    """
    t_pi = fit_results["t_max_transfer"]
    t_pi_err = fit_errs.get("t_max_transfer", float("nan"))
    f = 1.0 / (2.0 * t_pi)
    f_err = t_pi_err / (2.0 * t_pi * t_pi)
    return f, f_err


class _ClockRabiDiagnosticBase(ClockSpecPulseRatioFrag):
    """Shared clock-Rabi diagnostic: on-resonance, Rabi-flop fit over pulse time.

    Subclasses set ``_use_down_beam`` to pick the beam. The clock-shelving slice
    is intrinsic to ``ClockSpecPulseRatioFrag`` and left at its default ratio.
    """

    # Set by subclasses; selects the clock beam for the spectroscopy pulse.
    _use_down_beam: bool = False

    def build_fragment(self):
        super().build_fragment()

        # On resonance (OPLL at the clock line) for a clean flop.
        self.override_param("extra_clock_detuning", 0.0)

        # Pick the clock beam for this diagnostic.
        self.override_param("use_down_beam", self._use_down_beam)

        # Hold the velocity-selection slice FIXED across the scan. The default
        # T_sel = spectroscopy_pulse_time * pulse_ratio co-scales the slice with the
        # interrogation pulse, so a Rabi scan selects a different (and ever-narrower)
        # velocity class at every point - washing out the flop. A fixed selection
        # time (the nominal shelving duration) selects one velocity class so only the
        # interrogation pulse varies, restoring a clean flop. (This is scan-code, not
        # rig physics.)
        self.override_param(
            "selection_time_override", constants.CLOCK_SHELVING_PULSE_TIME
        )

        # EM gain on by default so the diagnostic is genuinely default-runnable
        # (the normalised fast-kinetics clock readout needs it). Enabled only via
        # the experiment's own flag; the DISABLE_EM_GAIN safety interlock is never
        # touched (the EMGainMixin reads it and aborts safely if it forbids gain).
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

    def get_default_analyses(self):
        # The clock readout is INVERTED: excitation_fraction is the surviving ground
        # population, so the flop starts HIGH (~1) at short pulse and DIPS at the pi
        # pulse. decaying_sinusoid expects a rise-from-zero flop whose t_max_transfer
        # is the pi pulse, so we fit 1 - excitation_fraction (a normal rise-from-zero
        # flop) and t_max_transfer then lands on the dip = the pi pulse.
        #
        # t_dead is left FREE (not pinned to 0): the flop genuinely starts after a
        # ~10 us dead-time (the OPLL gravity-comp ramp is still settling onto
        # resonance when the clock pulse begins), measured on RID 75720. Pinning
        # t_dead=0 forces the fit onto the wrong feature. The persisted fit also
        # averages the num_repeats duplicates (else decaying_sinusoid's initialiser
        # divides by a zero x-spacing -> inf) and drops the unphysical survival >1
        # outliers the normalised readout occasionally emits.
        # The live OnlineFit draws over the raw excitation_fraction channel (the
        # applet can only plot an existing result channel, not a transform). It is a
        # convenience overlay; the persisted dataset fit below is the deliverable and
        # fits 1 - excitation_fraction so its reported t_max_transfer is the physical
        # pi pulse (the dip). Both locate the same physical pi.
        return [
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.excitation_fraction,
                },
            )
        ] + make_dataset_fit_analysis(
            fit_type="decaying_sinusoid",
            x=self.spectroscopy_pulse_time,
            y=self.excitation_fraction,
            y_transform=lambda ys: 1.0 - ys,
            y_valid_range=(0.0, 1.05),
            average_repeats=True,
            outputs=[
                FitOutput(
                    "pi_time",
                    "Fitted clock pi-pulse time (dip of the inverted survival flop)",
                    fit_key="t_max_transfer",
                    unit="us",
                ),
                FitOutput(
                    "rabi_frequency",
                    "Clock Rabi frequency derived from the fitted pi-time",
                    derive=_rabi_frequency_from_pi_time,
                    unit="kHz",
                ),
            ],
        )


class ClockRabiDownBeamDiagnosticFrag(_ClockRabiDiagnosticBase):
    """Diagnostic 2 - clock Rabi frequency, DOWN beam (``use_down_beam=True``)."""

    _use_down_beam = True


class ClockRabiUpBeamDiagnosticFrag(_ClockRabiDiagnosticBase):
    """Diagnostic 3 - clock Rabi frequency, UP beam (``use_down_beam=False``)."""

    _use_down_beam = False


# NOTE: the scan MUST start at a nonzero pulse time. The clock delivery setpoint
# is auto-scaled as V = V_ref * (T_ref / T_clock)^2 in
# CompensatedClockSpecMixin.prepare_clock_delivery_aom, which divides by
# spectroscopy_pulse_time - a t=0 first point raises ZeroDivisionError on the core
# device and kills the run (observed RID 74681). Start at 5 us; the t=0 point
# (trivially excitation=0) is not needed for the flop fit.

# Diagnostic 2: down beam (pi ~68 us) -> scan 5..400 us (>=5 pi-times).
ClockRabiDownBeamDiagnostic = make_default_scan_exp(
    ClockRabiDownBeamDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="spectroscopy_pulse_time",
            start=5e-6,
            stop=400e-6,
            num_points=40,
        ),
    ],
    default_num_repeats=2,
)

# Diagnostic 3: up beam (pi ~55 us) -> scan 5..300 us (>=5 pi-times).
ClockRabiUpBeamDiagnostic = make_default_scan_exp(
    ClockRabiUpBeamDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="spectroscopy_pulse_time",
            start=5e-6,
            stop=300e-6,
            num_points=40,
        ),
    ],
    default_num_repeats=2,
)
