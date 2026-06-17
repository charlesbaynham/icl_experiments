"""
Tests for the LMT spacetime-trajectory inference (``lmt_trajectory``).

These exercise the consumer side of the ``pulse_record`` format emitted by
``PulseDMARecording``: decode the most recent valid record, build the event
sequence and infer the cloud trajectory. The physics is a port of ``lmt_sim``;
here we only pin the decode/selection logic and the basic shape invariants so
the applet has something it can rely on.
"""

import numpy as np
import pytest

from repository.lib.physics import lmt_trajectory as traj


def _record(directions, starts, durations, opll):
    """Build a genuine 7-row record; unused fields are zero-filled."""
    n = len(directions)
    zeros = [0.0] * n
    return [
        list(map(float, directions)),
        list(map(float, starts)),
        list(map(float, durations)),
        list(map(float, opll)),
        list(zeros),  # switch
        list(zeros),  # delivery
        list(zeros),  # setpoint
    ]


def _mach_zehnder_record():
    """A pi/2 - pi - pi/2 up-beam sequence with free evolution between pulses.

    ``build_sequence_from_lab_pulse_dump`` treats pulses longer than its 50 us
    threshold as pi pulses (rabi = 1/2T) and shorter ones as pi/2 (rabi = 1/4T),
    so the durations are chosen to land on the intended areas.
    """
    t_pi2 = 45e-6  # <= 50 us threshold -> pi/2
    t_pi = 90e-6  # > 50 us threshold  -> pi
    T = 1e-3  # interrogation time
    starts = [0.0, T, 2 * T]
    durations = [t_pi2, t_pi, t_pi2]
    directions = [1, 1, 1]
    opll = [0.0, 0.0, 0.0]
    return _record(directions, starts, durations, opll)


def test_most_recent_valid_record_skips_sentinels():
    real_a = _record([1], [0.0], [45e-6], [0.0])
    real_b = _record([1, 1], [0.0, 1e-3], [45e-6, 45e-6], [0.0, 0.0])
    same_as_last = [[traj.PULSE_RECORD_SAME_AS_LAST_SENTINEL]]
    disabled = [[traj.PULSE_RECORD_DISABLED_SENTINEL]]

    records = [real_a, real_b, disabled, same_as_last]
    got = traj.most_recent_valid_record(records)
    assert got is not None
    # real_b is the most recent genuine record (sentinels point back to it).
    assert len(got[0]) == 2


def test_most_recent_valid_record_none_when_only_sentinels():
    records = [[[traj.PULSE_RECORD_DISABLED_SENTINEL]]]
    assert traj.most_recent_valid_record(records) is None


def test_build_sequence_inserts_freefall_between_pulses():
    _ts, sequence = traj.build_sequence_from_lab_pulse_dump(
        is_up=[1, 1],
        start_times_s=[0.0, 1e-3],
        durations_s=[45e-6, 45e-6],
        opll_hz=[0.0, 0.0],
        switch_hz=[0.0, 0.0],
        delivery_hz=[0.0, 0.0],
        delivery_setpoint=[0.0, 0.0],
    )
    kinds = [type(e).__name__ for e in sequence]
    assert kinds == ["Pulse", "Freefall", "Pulse"]
    assert sequence[1].duration == pytest.approx(1e-3 - 45e-6)


def test_first_pulse_is_resonant_and_flips_ground():
    """A velocity-selection pi pulse (>50 us) flips m=0 ground -> m=+1 excited."""
    _ts, sequence = traj.build_sequence_from_lab_pulse_dump(
        is_up=[1],
        start_times_s=[0.0],
        durations_s=[90e-6],  # > 50 us threshold -> treated as a pi pulse
        opll_hz=[0.0],
        switch_hz=[0.0],
        delivery_hz=[0.0],
        delivery_setpoint=[0.0],
    )
    pulse = sequence[0]
    # By construction the first pulse is anchored on resonance for m=0 ground.
    assert traj._transition_probability(0, True, pulse) > 0.75
    # A sub-threshold pulse of the same family is a pi/2 (split): p ~ 0.5.
    _ts2, seq2 = traj.build_sequence_from_lab_pulse_dump(
        is_up=[1],
        start_times_s=[0.0],
        durations_s=[45e-6],  # <= 50 us threshold -> pi/2
        opll_hz=[0.0],
        switch_hz=[0.0],
        delivery_hz=[0.0],
        delivery_setpoint=[0.0],
    )
    assert traj._transition_probability(0, True, seq2[0]) == pytest.approx(
        0.5, abs=0.05
    )


def test_mach_zehnder_trajectory_shapes():
    record = _mach_zehnder_record()
    result = traj.infer_trajectory_from_pulse_record([record])
    assert result is not None
    sequence, clouds, clearout_times = result

    # pi/2 splits, pi flips, pi/2 recombines -> more than one branch.
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
        t_z, z, t_m, m, ground, m_ground = traj.build_plot_trace(sequence, cloud)
        assert len(t_z) == len(z) == len(ground)
        assert len(t_m) == len(m) == len(m_ground)
        assert np.all(np.diff(t_z) >= -1e-12)  # time is non-decreasing


def test_infer_returns_none_for_empty_record():
    empty = traj.infer_trajectory_from_pulse_record([_record([], [], [], [])])
    assert empty is None
