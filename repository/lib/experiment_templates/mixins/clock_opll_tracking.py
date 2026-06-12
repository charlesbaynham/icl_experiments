"""
Shared OPLL command wrappers for clock experiments.

This module defines :class:`ClockOPLLTrackingMixin`, a thin set of wrappers
around the ``clock_opll`` DDS / DRG ramper that *also* update the
frequency-tracking state read by
:meth:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording.register_pulse`.

Every code path that can drive the OPLL while a pulse is being recorded must go
through these wrappers (never the raw ``clock_opll.clock_frequency_ramper``),
otherwise the pulse recorder falls back to the stale static OPLL frequency and
records the wrong value. See the table in ``AGENTS.md`` ("Clock Pulse
Interactions").

The tracking *state* itself (``_tracked_opll_*``) and the
:meth:`_get_opll_instantaneous` reader live on
:class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`,
next to the pulse recorder it feeds. As with the existing convention, these
wrappers are mixed into the clock-specific bases next to the devices they drive
and rely on a concrete experiment also mixing in
``DipoleTrapWithExperimentBase`` to supply that state.
"""

from artiq.language import kernel
from artiq.language import now_mu
from numpy import int32

from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController


class ClockOPLLTrackingMixin(RedMOTWithExperimentBase):
    """
    OPLL command wrappers that keep the pulse-recorder tracking state in sync.

    Provides :meth:`set_clock_opll`, :meth:`start_clock_opll_ramp` and
    :meth:`stop_clock_opll_ramp`. A concrete experiment must also mix in
    :class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`
    (which creates the ``_tracked_opll_*`` state these wrappers update) and must
    create a ``clock_opll`` fragment.
    """

    clock_opll: ClockOPLLController

    @kernel
    def set_clock_opll(self, freq: float):
        """Set the OPLL offset DDS to a static frequency (and track it)."""
        self.clock_opll.clock_OPLL_offset.set(freq)
        self._tracked_opll_freq = freq
        self._tracked_opll_ramp_active = False

    @kernel
    def start_clock_opll_ramp(
        self,
        rate: float,
        freq_low: float,
        freq_high: float,
        wave_type: int32,
    ):
        """Start a DRG ramp on the OPLL offset DDS (and track it)."""
        self.clock_opll.clock_frequency_ramper.start_ramp(
            rate, freq_low, freq_high, wave_type=wave_type
        )
        self._tracked_opll_ramp_rate = rate
        self._tracked_opll_ramp_low = freq_low
        self._tracked_opll_ramp_high = freq_high
        self._tracked_opll_ramp_wave = wave_type
        self._tracked_opll_ramp_start_mu = now_mu()
        self._tracked_opll_ramp_active = True

    @kernel
    def stop_clock_opll_ramp(self):
        """Stop the OPLL DRG ramp (and track that it is no longer active)."""
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        self._tracked_opll_ramp_active = False
