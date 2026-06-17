"""
Unit tests for the OPLL frequency tracking that feeds the pulse recorder.

These pin down the fix for the "stale static OPLL" bug: a clock pulse fired
while a DRG ramp is running must record the OPLL frequency at the *centre* of
the pulse, not the pre-ramp static set-point. This only works if every ramp is
started/stopped through the tracking wrappers
(:class:`ClockOPLLTrackingMixin`), which keep the ``_tracked_opll_*`` state in
sync with the hardware.

Rather than build a full (device-heavy) experiment fragment, we drive the real
``set_clock_opll`` / ``start_clock_opll_ramp`` / ``stop_clock_opll_ramp``
wrappers, the real ``DipoleTrapWithExperimentBase._get_opll_instantaneous``
reader and the real ``PulseDMARecording.register_pulse`` recorder against a
lightweight object that carries the tracked state. The OPLL hardware itself is
mocked; the arithmetic under test is pure Python.
"""

from unittest.mock import MagicMock

import pytest
from artiq.language import core as core_language
from numpy import int32
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.clock_opll_tracking import (
    ClockOPLLTrackingMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    CLOCK_HIGH_RAMP_FREQ,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    CLOCK_LOW_RAMP_FREQ,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutBase,
)
from repository.lib.fragments.pulse_recorder_and_tracker import BUFFER_DEPTH
from repository.lib.fragments.pulse_recorder_and_tracker import PulseDMARecording

RAMP_RATE = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
STATIC_OPLL = 80e6


def _raw(method):
    """Unwrap an ``@kernel``/``@portable`` decorated method to its plain
    Python function so it can be executed directly on the host."""
    return method.artiq_embedded.function


class _MuTimeManager:
    """Minimal ARTIQ time manager that tracks a machine-unit cursor so that
    ``now_mu()`` is controllable from the host."""

    def __init__(self):
        self.t = int64(0)

    def get_time_mu(self):
        return self.t

    def set_time_mu(self, t):
        self.t = int64(t)

    def take_time_mu(self, dt):
        self.t += int64(dt)

    def take_time(self, dt):  # seconds
        self.t += int64(round(dt / 1e-9))

    def enter_sequential(self):
        pass

    def enter_parallel(self):
        pass

    def exit(self):
        pass


@pytest.fixture
def mu_clock():
    previous = core_language._time_manager
    clock = _MuTimeManager()
    core_language.set_time_manager(clock)
    try:
        yield clock
    finally:
        core_language.set_time_manager(previous)


class _Outer:
    """Stands in for the experiment object: holds the tracked OPLL state plus
    the real wrapper / reader methods."""

    # Real methods under test, unwrapped to plain functions.
    set_clock_opll = _raw(ClockOPLLTrackingMixin.set_clock_opll)
    start_clock_opll_ramp = _raw(ClockOPLLTrackingMixin.start_clock_opll_ramp)
    stop_clock_opll_ramp = _raw(ClockOPLLTrackingMixin.stop_clock_opll_ramp)
    start_clock_frequency_ramp = _raw(
        ClockShelvingAndClearoutBase.start_clock_frequency_ramp
    )
    _get_opll_instantaneous = _raw(DipoleTrapWithExperimentBase._get_opll_instantaneous)

    def __init__(self, core):
        self.core = core
        self._clock_opll = MagicMock()
        # Mirror the tracking-state defaults set in
        # DipoleTrapWithExperimentBase.build_fragment.
        self._tracked_opll_freq = STATIC_OPLL
        self._tracked_opll_ramp_active = False
        self._tracked_opll_ramp_rate = 0.0
        self._tracked_opll_ramp_low = STATIC_OPLL
        self._tracked_opll_ramp_high = STATIC_OPLL
        self._tracked_opll_ramp_wave = int32(0)
        self._tracked_opll_ramp_start_mu = int64(0)
        self._tracked_up_switch_freq = 0.0
        self._tracked_down_switch_freq = 0.0
        self._tracked_delivery_aom_freq = 0.0
        self._tracked_delivery_aom_setpoint = 0.0


class _Recorder:
    """Stands in for the PulseDMARecording fragment: holds the record buffers
    plus the real ``register_pulse`` recorder (which now records the pulse
    facts and a default-intent entry together)."""

    register_pulse = _raw(PulseDMARecording.register_pulse)
    register_pulse_with_intent = _raw(PulseDMARecording.register_pulse_with_intent)
    _append_intent = _raw(PulseDMARecording._append_intent)

    def __init__(self, core, outer):
        self.core = core
        self.outer_self = outer
        self._pulse_record_start_times_mu = [int64(0)] * BUFFER_DEPTH
        self._pulse_record_durations_mu = [int64(0)] * BUFFER_DEPTH
        self._pulse_record_directions = [int32(0)] * BUFFER_DEPTH
        self._pulse_record_opll_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_switch_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_setpoint = [0.0] * BUFFER_DEPTH
        self._pulse_record_num_pulses = 0
        # Intent stream buffers (register_pulse appends a default-intent entry)
        self._intent_record_start_times_mu = [int64(0)] * BUFFER_DEPTH
        self._intent_record_durations_mu = [int64(0)] * BUFFER_DEPTH
        self._intent_record_kinds = [int32(0)] * BUFFER_DEPTH
        self._intent_record_state_effects = [int32(0)] * BUFFER_DEPTH
        self._intent_record_addressed_states = [int32(0)] * BUFFER_DEPTH
        self._intent_record_addressed_m = [int32(0)] * BUFFER_DEPTH
        self._intent_record_delta_m = [int32(0)] * BUFFER_DEPTH
        self._intent_record_num_events = 0


@pytest.fixture
def harness(device_mgr, mu_clock):
    core = device_mgr.get("core")
    outer = _Outer(core)
    recorder = _Recorder(core, outer)
    return core, outer, recorder, mu_clock


def test_recorded_opll_tracks_active_ramp(harness):
    """A pulse fired during a tracked ramp records the OPLL at the pulse centre,
    not the stale static set-point."""
    core, outer, recorder, clock = harness

    t_ramp_start = int64(1_000_000)
    clock.set_time_mu(t_ramp_start)
    outer.start_clock_opll_ramp(
        RAMP_RATE, CLOCK_LOW_RAMP_FREQ, CLOCK_HIGH_RAMP_FREQ, int32(0)
    )
    assert outer._tracked_opll_ramp_active is True
    assert outer._tracked_opll_ramp_start_mu == t_ramp_start

    # The pulse starts at the moment the ramp started (t=0 into the ramp).
    duration_s = 380e-6
    recorder.register_pulse(is_up=True, duration_s=duration_s)

    # register_pulse records the mean of the instantaneous OPLL at pulse start
    # and end; with the pulse starting at the ramp origin that is the value at
    # the pulse centre.
    duration_mu = core.seconds_to_mu(duration_s)
    expected_centre = (
        CLOCK_LOW_RAMP_FREQ + RAMP_RATE * core.mu_to_seconds(duration_mu) / 2.0
    )

    recorded = recorder._pulse_record_opll_freq_hz[0]
    assert recorded == pytest.approx(expected_centre)
    # Crucially NOT the stale static value (this is the bug being fixed).
    assert recorded != STATIC_OPLL
    assert recorded > STATIC_OPLL
    # ~2.67 kHz above 80 MHz for a 380 us pulse.
    assert recorded - STATIC_OPLL == pytest.approx(2670, abs=50)


def test_recorded_opll_static_after_tracked_stop(harness):
    """After a tracked stop, a registered pulse records the static frequency."""
    core, outer, recorder, clock = harness

    clock.set_time_mu(int64(1_000_000))
    outer.start_clock_opll_ramp(
        RAMP_RATE, CLOCK_LOW_RAMP_FREQ, CLOCK_HIGH_RAMP_FREQ, int32(0)
    )
    clock.set_time_mu(int64(2_000_000))
    outer.stop_clock_opll_ramp()
    assert outer._tracked_opll_ramp_active is False

    recorder.register_pulse(is_up=True, duration_s=380e-6)
    assert recorder._pulse_record_opll_freq_hz[0] == STATIC_OPLL


def test_set_clock_opll_records_new_static(harness):
    """set_clock_opll updates the recorded static frequency."""
    core, outer, recorder, clock = harness

    outer.set_clock_opll(80.5e6)
    assert outer._tracked_opll_ramp_active is False

    recorder.register_pulse(is_up=True, duration_s=100e-6)
    assert recorder._pulse_record_opll_freq_hz[0] == pytest.approx(80.5e6)


def test_shelving_ramp_goes_through_tracker(harness):
    """Regression test for the reported symptom: the clock-shelving ramp must
    update the tracking state (it previously called the raw ramper, leaving the
    recorder blind to the active ramp)."""
    core, outer, recorder, clock = harness

    t_ramp_start = int64(5_000_000)
    clock.set_time_mu(t_ramp_start)
    # This is the real ClockShelvingAndClearoutBase method that used to bypass
    # the tracker.
    outer.start_clock_frequency_ramp()

    assert outer._tracked_opll_ramp_active is True
    assert outer._tracked_opll_ramp_rate == RAMP_RATE
    assert outer._tracked_opll_ramp_low == CLOCK_LOW_RAMP_FREQ
    assert outer._tracked_opll_ramp_high == CLOCK_HIGH_RAMP_FREQ
    assert outer._tracked_opll_ramp_start_mu == t_ramp_start

    # And a pulse fired during it records a ramped (non-static) value.
    recorder.register_pulse(is_up=True, duration_s=380e-6)
    assert recorder._pulse_record_opll_freq_hz[0] != STATIC_OPLL
