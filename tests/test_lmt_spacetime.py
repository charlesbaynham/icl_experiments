"""
Tests for the intent-driven LMT spacetime reconstruction (``lmt_spacetime``).

These exercise the consumer side of the ``pulse_intent_record`` format emitted
by ``PulseDMARecording``: decode the most recent valid record, build the intent
events and walk them into cloud trajectories. The branch semantics mirror
``repository.lib.physics.trajectory``; here we pin the decode/selection logic
and the basic shape invariants the applet relies on.
"""

import numpy as np
import pytest

from repository.lib.physics import lmt_resonance as pi
from repository.lib.physics import lmt_spacetime as st


def _record(events):
    """Build a genuine 7-row intent record from a list of event dicts.

    Row order matches ``PulseDMARecording._save_intent_record_to_dataset``:
    ``[kinds, start_times_s, durations_s, state_effects, addressed_states,
    addressed_m, delta_m]``.
    """
    keys = (
        "kind",
        "t_start_s",
        "duration_s",
        "state_effect",
        "addressed_state",
        "addressed_m",
        "delta_m",
    )
    return [[float(e[k]) for e in events] for k in keys]


def _pulse(t_start, duration, effect, state, m, delta_m):
    return {
        "kind": pi.Kind.PULSE,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": effect,
        "addressed_state": state,
        "addressed_m": m,
        "delta_m": delta_m,
    }


def _clearout(t_start, duration, state=pi.AddressedState.GROUND):
    return {
        "kind": pi.Kind.CLEAROUT,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": pi.StateEffect.NONE,
        "addressed_state": state,
        "addressed_m": pi.M_AUTO,
        "delta_m": 0,
    }


def _symmetric_mach_zehnder_events():
    """Declared up-beam pi/2 - pi - pi/2 Mach-Zehnder on the (g,0)<->(e,1) pair."""
    t_pulse = 30e-6
    T = 1e-3
    return [
        _pulse(0.0, t_pulse, pi.StateEffect.SUPERPOSE, pi.AddressedState.GROUND, 0, +1),
        _pulse(T, t_pulse, pi.StateEffect.FLIP, pi.AddressedState.GROUND, 0, +1),
        _pulse(
            2 * T, t_pulse, pi.StateEffect.SUPERPOSE, pi.AddressedState.GROUND, 0, +1
        ),
    ]


def test_most_recent_valid_record_skips_sentinels():
    real_a = _record(
        [_pulse(0.0, 30e-6, pi.StateEffect.FLIP, pi.AddressedState.GROUND, 0, +1)]
    )
    real_b = _record(_symmetric_mach_zehnder_events())
    same_as_last = [[st.INTENT_RECORD_SAME_AS_LAST_SENTINEL]]
    disabled = [[st.INTENT_RECORD_DISABLED_SENTINEL]]

    records = [real_a, real_b, disabled, same_as_last]
    got = st.most_recent_valid_record(records)
    assert got is not None
    # real_b (3 events) is the most recent genuine record.
    assert len(got[0]) == 3


def test_most_recent_valid_record_none_when_only_sentinels():
    records = [[[st.INTENT_RECORD_DISABLED_SENTINEL]]]
    assert st.most_recent_valid_record(records) is None


def test_pi2_superpose_splits_ground_into_two_branches():
    events = st.intent_events_from_record(
        _record(
            [
                _pulse(
                    0.0,
                    30e-6,
                    pi.StateEffect.SUPERPOSE,
                    pi.AddressedState.GROUND,
                    0,
                    +1,
                )
            ]
        )
    )
    sequence, clouds, clearout_times = st.walk_intent_to_trajectory(events)
    assert clearout_times.size == 0
    # One branch stays |g,0>, the other transfers to |e,1>.
    finals = sorted((c.is_ground[-1], c.m[-1]) for c in clouds)
    assert finals == [(False, 1), (True, 0)]


def test_symmetric_mach_zehnder_trajectory_shapes():
    record = _record(_symmetric_mach_zehnder_events())
    result = st.infer_trajectory_from_intent_record([record])
    assert result is not None
    sequence, clouds, clearout_times = result

    # pi/2 splits, pi swaps the arms, pi/2 recombines -> more than one branch.
    assert len(clouds) >= 2
    assert clearout_times.size == 0

    # Every cloud history is internally consistent in length.
    for cloud in clouds:
        n = len(cloud.times)
        assert len(cloud.z) == n
        assert len(cloud.m) == n
        assert len(cloud.is_ground) == n

    # build_plot_trace returns matched-length arrays usable by the applet.
    for cloud in clouds:
        t_z, z, t_m, m, ground, m_ground = st.build_plot_trace(sequence, cloud)
        assert len(t_z) == len(z) == len(ground)
        assert len(t_m) == len(m) == len(m_ground)
        assert np.all(np.diff(t_z) >= -1e-12)  # time is non-decreasing


def test_clearout_kills_ground_and_records_time():
    events = st.intent_events_from_record(
        _record(
            [
                # split into |g,0> + |e,1>, then clear the ground port.
                _pulse(
                    0.0,
                    30e-6,
                    pi.StateEffect.SUPERPOSE,
                    pi.AddressedState.GROUND,
                    0,
                    +1,
                ),
                _clearout(1e-3, 5e-6, state=pi.AddressedState.GROUND),
            ]
        )
    )
    sequence, clouds, clearout_times = st.walk_intent_to_trajectory(events)
    assert clearout_times.size == 1
    # The |g,0> branch is cleared (dead), the |e,1> branch survives.
    dead = [c for c in clouds if not c.alive]
    alive = [c for c in clouds if c.alive]
    assert len(dead) == 1 and dead[0].is_ground[-1] is True
    assert len(alive) == 1 and alive[0].is_ground[-1] is False


def test_gap_inserts_drift_event():
    events = st.intent_events_from_record(
        _record(
            [
                _pulse(
                    0.0, 30e-6, pi.StateEffect.FLIP, pi.AddressedState.GROUND, 0, +1
                ),
                _pulse(
                    1e-3, 30e-6, pi.StateEffect.FLIP, pi.AddressedState.GROUND, 0, +1
                ),
            ]
        )
    )
    sequence, _clouds, _ct = st.walk_intent_to_trajectory(events)
    kinds = [type(e).__name__ for e in sequence]
    assert kinds == ["Pulse", "Drift", "Pulse"]
    assert sequence[1].duration == pytest.approx(1e-3 - 30e-6)


def test_infer_returns_none_for_empty_or_disabled():
    assert st.infer_trajectory_from_intent_record([_record([])]) is None
    assert (
        st.infer_trajectory_from_intent_record([[[st.INTENT_RECORD_DISABLED_SENTINEL]]])
        is None
    )
