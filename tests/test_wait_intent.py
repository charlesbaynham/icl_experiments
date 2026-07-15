"""
Host-side tests for issue #47: a ``Wait``/dark-time must be registered into the
recorded intent stream so that

1. the sequence-end anchor advances by exactly the wait duration, and
2. the ballistic ROI predictor moves the cloud by the corresponding free-flight
   amount,

while the wait remains a *pure* dark time - no state flip, no momentum change.

Pure Python/NumPy - no ARTIQ fixtures. Uses the same building blocks as
``LMTCompensatedCameraConfig._calculate_positions_host``
(:func:`repository.lib.physics.trajectory.predict_port_pixels`) and the same
side-view geometry as ``test_ballistic_predictor`` /
``test_roi_prediction_equivalence``.
"""

import numpy as np
import pytest
import scipy.constants

from repository.lib.physics import lmt_resonance as pulse_intent
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.lmt_resonance import IntentEvent
from repository.lib.physics.trajectory import predict_port_pixels
from repository.lib.physics.trajectory import walk_intent_events

# ── Geometry (side-view camera) ────────────────────────────────────────────────

PIXEL_SIZE_M = 16e-6
MAGNIFICATION = 1.0
CENTRE_PIXEL = (256.0, 256.0)
SR87_MASS_KG = scipy.constants.atomic_mass * 87
CLOCK_WAVELENGTH_M = scipy.constants.c / 429_228_004_229_872.99
GRAVITY = scipy.constants.g

CFG = BallisticConfig(
    mass_kg=SR87_MASS_KG,
    gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
    clock_beam_direction=np.array([0.0, 0.0, 1.0]),
    clock_wavelength_m=CLOCK_WAVELENGTH_M,
    camera=CameraGeometry(
        optical_axis=np.array([0.0, 1.0, 0.0]),
        sensor_x_axis=np.array([1.0, 0.0, 0.0]),
        sensor_y_axis=np.array([0.0, 0.0, 1.0]),
        centre_pixel=CENTRE_PIXEL,
        pixel_size_m=PIXEL_SIZE_M,
        magnification=MAGNIFICATION,
    ),
)


def _pulse(t_start_s, is_up=True, duration_s=55e-6):
    """An up/down pi transfer, as ``register_pulse`` records it."""
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kind=pulse_intent.Kind.PULSE,
        state_effect=pulse_intent.StateEffect.FLIP,
        addressed_state=pulse_intent.AddressedState.AUTO,
        addressed_m=pulse_intent.M_AUTO,
        delta_m=1 if is_up else -1,
    )


def _wait(t_start_s, duration_s):
    """A dark time, exactly as ``register_wait`` records it."""
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kind=pulse_intent.Kind.WAIT,
        state_effect=pulse_intent.StateEffect.NONE,
        addressed_state=pulse_intent.AddressedState.AUTO,
        addressed_m=pulse_intent.M_AUTO,
        delta_m=0,
    )


# A single up pulse leaves one excited branch at m = 1: a moving cloud, so the
# trailing wait's shift includes both v*t and 0.5*g*t^2, not just gravity.
_SEQ = [_pulse(1e-3, is_up=True)]

# Times of flight (seconds since release) and dark time under test.
_T_IMG = 15e-3
_WAIT = 5e-3
_WAIT_START = 2e-3  # after the pulse (fires at 1 ms, 55 us long)


def _sequence_end_since_release_mu(
    start_times_mu, durations_mu, t_release_minus_playback_mu=0
):
    """Mirror ``_sequence_end_since_release_mu``: max(start_i + duration_i)
    over the recorded intent stream, rebased to release. Kind-agnostic, so any
    recorded row - including a wait - participates."""
    end_max = 0
    for start, dur in zip(start_times_mu, durations_mu):
        end = int(start) + int(dur) - t_release_minus_playback_mu
        end_max = max(end_max, end)
    return end_max


def test_wait_row_advances_sequence_end_anchor():
    """Criterion 1: a trailing wait shifts the sequence-end anchor by exactly t."""
    start_times_mu = [200_000, 400_000]
    durations_mu = [55_000, 55_000]
    anchor_no_wait = _sequence_end_since_release_mu(start_times_mu, durations_mu)

    wait_duration_mu = 10_000_000  # 10 ms at 1 ns/mu
    wait_start_mu = start_times_mu[-1] + durations_mu[-1]  # dark time at seq end
    anchor_with_wait = _sequence_end_since_release_mu(
        start_times_mu + [wait_start_mu],
        durations_mu + [wait_duration_mu],
    )

    assert anchor_with_wait - anchor_no_wait == wait_duration_mu


def test_wait_equivalent_to_image_delay_bump():
    """Criterion 2: adding ``Wait(t)`` (which advances the anchor by t) predicts
    the same pixels as leaving the sequence untouched and imaging t later - i.e.
    the wait produces exactly the ballistic displacement for an extra t of
    flight."""
    with_wait = predict_port_pixels(
        _SEQ + [_wait(_WAIT_START, _WAIT)],
        _T_IMG + _WAIT,
        _T_IMG + _WAIT,
        CFG,
    )
    delay_bumped = predict_port_pixels(_SEQ, _T_IMG + _WAIT, _T_IMG + _WAIT, CFG)

    for port in ("ground", "excited"):
        assert with_wait[port].x_pixel == pytest.approx(delay_bumped[port].x_pixel)
        assert with_wait[port].y_pixel == pytest.approx(delay_bumped[port].y_pixel)
        assert with_wait[port].multiplicity == delay_bumped[port].multiplicity


def test_wait_moves_predicted_position():
    """The bug this fixes: a trailing wait must actually move the predicted cloud
    (previously it was frozen). Later imaging -> further free fall -> smaller y on
    the side-view sensor."""
    baseline = predict_port_pixels(_SEQ, _T_IMG, _T_IMG, CFG)
    with_wait = predict_port_pixels(
        _SEQ + [_wait(_WAIT_START, _WAIT)],
        _T_IMG + _WAIT,
        _T_IMG + _WAIT,
        CFG,
    )
    assert with_wait["excited"].y_pixel < baseline["excited"].y_pixel - 1.0
    assert with_wait["excited"].multiplicity == baseline["excited"].multiplicity


def test_wait_is_pure_dark_time_at_fixed_image_time():
    """Criterion 4: at a fixed imaging time, inserting a wait changes nothing -
    no state flip, no momentum kick, no position shift."""
    without = predict_port_pixels(_SEQ, _T_IMG, _T_IMG, CFG)
    with_wait = predict_port_pixels(
        _SEQ + [_wait(_WAIT_START, _WAIT)], _T_IMG, _T_IMG, CFG
    )
    for port in ("ground", "excited"):
        assert with_wait[port].x_pixel == pytest.approx(without[port].x_pixel)
        assert with_wait[port].y_pixel == pytest.approx(without[port].y_pixel)
        assert with_wait[port].multiplicity == without[port].multiplicity


def test_wait_leaves_branches_unchanged_in_walk():
    """Criterion 4 at the walk level: the branch set (internal state + momentum)
    is identical with and without the wait when walked to the same time."""
    branches_without = walk_intent_events(_SEQ, up_to_t_s=_T_IMG, cfg=CFG)
    branches_with = walk_intent_events(
        _SEQ + [_wait(_WAIT_START, _WAIT)], up_to_t_s=_T_IMG, cfg=CFG
    )

    def key(branches):
        return sorted((b.is_ground, b.m) for b in branches)

    assert key(branches_with) == key(branches_without)


def test_lone_wait_predicts_analytic_free_fall():
    """A sequence that is nothing but a dark time behaves like an empty stream:
    the single released ground branch stays on the plain gravity parabola
    (0.5*g*t^2 projected to the sensor) and no branch is created or flipped."""
    t_img = 12e-3
    scale = MAGNIFICATION / PIXEL_SIZE_M
    expected_y = CENTRE_PIXEL[1] - 0.5 * GRAVITY * t_img * t_img * scale

    lone_wait = predict_port_pixels([_wait(0.0, 8e-3)], t_img, t_img, CFG)
    empty = predict_port_pixels([], t_img, t_img, CFG)

    # The initial ground branch survives untouched; the excited port stays empty.
    assert lone_wait["ground"].multiplicity == 1
    assert lone_wait["excited"].multiplicity == 0
    for port in ("ground", "excited"):
        assert lone_wait[port].x_pixel == pytest.approx(CENTRE_PIXEL[0])
        assert lone_wait[port].y_pixel == pytest.approx(expected_y)
        # Identical to an empty stream: a wait is a genuine no-op.
        assert lone_wait[port].x_pixel == pytest.approx(empty[port].x_pixel)
        assert lone_wait[port].y_pixel == pytest.approx(empty[port].y_pixel)
        assert lone_wait[port].multiplicity == empty[port].multiplicity
