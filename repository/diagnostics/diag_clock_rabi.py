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
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp

logger = logging.getLogger(__name__)


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

        # EM gain on by default so the diagnostic is genuinely default-runnable
        # (the normalised fast-kinetics clock readout needs it). Enabled only via
        # the experiment's own flag; the DISABLE_EM_GAIN safety interlock is never
        # touched (the EMGainMixin reads it and aborts safely if it forbids gain).
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

    def get_default_analyses(self):
        # Excitation-fraction-from-zero Rabi flop; t_dead pinned to 0 (the WS1
        # 689-spectroscopy convention). pi_time annotation = t_max_transfer.
        return [
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.excitation_fraction,
                },
                constants={"t_dead": 0},
            )
        ]


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
