r"""
Diagnostic 5 - Clock line centre (single weak pulse, frequency scan).

The simplest clock diagnostic: a *single* clock pulse whose frequency is scanned
across the transition, fitting the line centre. Unlike the clock-Rabi diagnostics
(:mod:`repository.diagnostics.diag_clock_rabi`), there is **no** velocity-selection
("slicing"/shelving) pulse and **no** second interrogation pulse - just one pulse,
then the normalised fast-kinetics readout.

The pulse area is deliberately small - ``pulse_area_fraction * pi`` (default
``pi/8``). A weak pulse keeps the interrogation in the linear (low-excitation)
regime, so off-resonant atoms are barely driven: this avoids the power broadening
that a full ``pi`` pulse would produce (off-resonant atoms still flip at high
Rabi frequency, washing out and broadening the line). The result is a narrow,
cleanly-fittable line whose centre tracks the transition frequency.

This wraps the existing clock-spectroscopy machinery
(``ClockSpecPulseRatioFrag`` = ``CompensatedClockSpecMixin`` + the XODT /
fast-kinetics stack) for loading, evaporation, the gravity-compensated clock
delivery, and the normalised excitation readout. Only the clock *sequence* is
replaced: ``do_experiment_after_dipole_trap_hook`` is overridden to fire one
weak, frequency-scanned pulse instead of the standard shelve-then-interrogate
pair.

Diagnosed quantity: the transition centre, via a ``lorentzian`` ``OnlineFit`` over
``extra_clock_detuning`` (the scanned detuning added to the OPLL frequency) vs
``excitation_fraction``. Since velocity selection is skipped, the line sits on
the full (Doppler-broadened) cloud; the weak pulse ensures the lineshape is not
*additionally* power-broadened, so the fitted centre is a faithful line-centre.

Pulse-area scaling: the clock delivery setpoint auto-scales to a ``pi`` pulse as
``V = V_ref * (T_ref / T)^2``; multiplying by ``pulse_area_fraction^2`` gives
``Omega * T = pulse_area_fraction * pi`` (area independent of the pulse duration,
which is then free to set the Fourier-limited linewidth).

Gravity compensation: with no shelving pulse to reference, the OPLL gravity ramp
is referenced to release (``t_dipole_beams_off``) rather than to the selection
pulse, and tracks the free-fall Doppler shift across the (single) pulse.

Beam selection (``use_down_beam``):

* up beam   -> ``use_down_beam = False`` (the param default)
* down beam -> ``use_down_beam = True``

EM gain is enabled by default in the experiment (``em_gain_enabled = True``,
``em_gain = 30``) so a default ``arguments={}`` run is self-sufficient. Gain is
enabled only via the experiment's own flag; the ``DISABLE_EM_GAIN`` safety
interlock is never touched.
"""

import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import OnlineFit
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.clock_spectroscopy.clock_spectroscopy_pulse_ratio import (
    ClockSpecPulseRatioFrag,
)
from repository.lib import constants
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    CLOCK_BEAM_DELIVERY_INFO,
)
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import ramp_rate
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    start_opll_offset,
)

logger = logging.getLogger(__name__)

# Default fraction of a pi pulse for the (weak) interrogation pulse. pi/8 keeps
# the excitation small so off-resonant atoms are barely driven -> no power
# broadening.
_DEFAULT_PULSE_AREA_FRACTION = 0.125


class _ClockLineCentreDiagnosticBase(ClockSpecPulseRatioFrag):
    """Single weak clock pulse, frequency scanned, line-centre fit.

    Subclasses set ``_use_down_beam`` to pick the clock beam. No velocity
    selection and no second pulse: ``do_experiment_after_dipole_trap_hook`` is
    overridden to fire one ``pulse_area_fraction * pi`` pulse.
    """

    # Set by subclasses; selects the clock beam for the single pulse.
    _use_down_beam: bool = False

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "pulse_area_fraction",
            FloatParam,
            "Pulse area as a fraction of pi (small -> weak -> no power broadening)",
            default=_DEFAULT_PULSE_AREA_FRACTION,
            min=1e-3,
            max=1.0,
        )
        self.pulse_area_fraction: FloatParamHandle

        # Pick the clock beam for this diagnostic.
        self.override_param("use_down_beam", self._use_down_beam)

        # NB: do NOT override_param("extra_clock_detuning", ...) here - it is the
        # default scan axis, so it must stay a *free* parameter. Overriding it
        # fixes its value and removes it from the free set, which makes
        # default_scan's FQN resolver raise "Default scan axis parameter
        # 'extra_clock_detuning' not found as a free parameter". Its parent
        # default is already 0.0 (centred on the line), so no override is needed.

        # Pulse duration sets the Fourier-limited linewidth; the area is fixed at
        # pulse_area_fraction * pi by the setpoint scaling regardless of duration.
        self.override_param("spectroscopy_pulse_time", constants.CLOCK_PI_TIME)

        # EM gain on by default so the diagnostic is genuinely default-runnable
        # (the normalised fast-kinetics clock readout needs it). Enabled only via
        # the experiment's own flag; the DISABLE_EM_GAIN safety interlock is never
        # touched (the EMGainMixin reads it and aborts safely if it forbids gain).
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Single weak clock pulse, frequency scanned: NO velocity-selection
        # (shelving) pulse and NO second interrogation pulse. The pulse area is
        # pulse_area_fraction * pi (default pi/8) so off-resonant atoms are barely
        # driven -> no power broadening -> a narrow, cleanly-fittable line.
        self.t_dipole_beams_off = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        T_clock = self.spectroscopy_pulse_time.get()
        T_ref = self.reference_pi_pulse_duration.get()
        V_ref = self.reference_clock_setpoint.get()
        f = self.pulse_area_fraction.get()

        # pi-pulse setpoint auto-scaling V = V_ref * (T_ref / T)^2, then * f^2 so
        # that Omega * T = f * pi (area ~ pi/8 by default), independent of T_clock.
        auto_setpoint = V_ref * (T_ref / T_clock) * (T_ref / T_clock) * f * f

        # Configure the delivery AOM (weak setpoint) and pre-position the OPLL,
        # done "in the past" via the preempt window then returning to _t_prep.
        _t_prep = now_mu()
        delay(-self.clock_delivery_preempt_time.get())
        self.clock_delivery_setter.set_suservo(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            amplitude=self.clock_delivery_handles.initial_amplitude_handle.get(),
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=auto_setpoint,
            enable_iir=True,
        )
        self.set_clock_delivery_aom(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            setpoint_v=auto_setpoint,
        )
        self.set_clock_opll(freq=start_opll_offset + self.extra_clock_detuning.get())
        self.after_clock_delivery_setup_hook(_t_prep)
        at_mu(_t_prep)

        # Fire the single pulse, gravity-compensated relative to release
        # (t_dipole_beams_off), with the scanned detuning added to the OPLL.
        t_start = now_mu() + self.core.seconds_to_mu(50e-6)
        total_ramp_time = self.core.mu_to_seconds(t_start - self.t_dipole_beams_off)

        if self.use_down_beam.get():
            opll_freq = (
                start_opll_offset
                - total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )
            # Raw ramper (mirrors the proven spectroscopy-pulse path in
            # CompensatedClockSpecMixin); register_pulse keeps the pulse recorder
            # in sync, as required for clock interactions.
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                opll_freq - 1e6,
                opll_freq,
                wave_type=2,
            )
            self.register_pulse(is_up=False, duration_s=T_clock)
            self.clock_down_dds.sw.on()
            delay(T_clock)
            self.clock_down_dds.sw.off()
        else:
            opll_freq = (
                start_opll_offset
                + total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                opll_freq,
                opll_freq + 2e6,
                wave_type=1,
            )
            self.register_pulse(is_up=True, duration_s=T_clock)
            self.clock_up_dds.sw.on()
            delay(T_clock)
            self.clock_up_dds.sw.off()

        delay(self.delay_after_spectroscopy.get())

    def get_default_analyses(self):
        # Line-centre fit on the clock detuning axis (excited-fraction peak).
        return [
            OnlineFit(
                "lorentzian",
                data={
                    "x": self.extra_clock_detuning,
                    "y": self.excitation_fraction,
                },
            )
        ]


class ClockLineCentreUpBeamDiagnosticFrag(_ClockLineCentreDiagnosticBase):
    """Diagnostic 5 - clock line centre, UP beam (``use_down_beam=False``)."""

    _use_down_beam = False


class ClockLineCentreDownBeamDiagnosticFrag(_ClockLineCentreDiagnosticBase):
    """Diagnostic 5 - clock line centre, DOWN beam (``use_down_beam=True``)."""

    _use_down_beam = True


# Default-runnable detuning scan across the clock line. +-50 kHz, 41 points,
# 2 repeats. The range/points are a starting point: tune on hardware to span a
# few linewidths and fold any tuned value back into repository/lib/constants.py.
ClockLineCentreUpBeamDiagnostic = make_default_scan_exp(
    ClockLineCentreUpBeamDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="extra_clock_detuning",
            start=-50e3,
            stop=50e3,
            num_points=41,
        ),
    ],
    default_num_repeats=2,
)

ClockLineCentreDownBeamDiagnostic = make_default_scan_exp(
    ClockLineCentreDownBeamDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="extra_clock_detuning",
            start=-50e3,
            stop=50e3,
            num_points=41,
        ),
    ],
    default_num_repeats=2,
)
