"""
Unit tests for the intent-driven trajectory predictor
(repository.lib.physics.trajectory) and its geometry building blocks
(repository.lib.physics.ballistic).

All tests are pure Python/NumPy - no ARTIQ fixtures required.
"""

import numpy as np
import pytest
import scipy.constants

from repository.lib.physics import lmt_resonance as pulse_intent
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.ballistic import recoil_velocity
from repository.lib.physics.lmt_resonance import IntentEvent
from repository.lib.physics.lmt_resonance import intent_events_from_arrays
from repository.lib.physics.trajectory import predict_port_pixels
from repository.lib.physics.trajectory import rebase_record_times_mu
from repository.lib.physics.trajectory import walk_intent_events

# ── Helpers ───────────────────────────────────────────────────────────────────

PIXEL_SIZE_M = 16e-6
MAGNIFICATION = 1.0
CENTRE_PIXEL = (256.0, 256.0)

SR87_MASS_KG = scipy.constants.atomic_mass * 87
CLOCK_WAVELENGTH_M = scipy.constants.c / 429_228_004_229_872.99  # 698 nm clock

GRAVITY = scipy.constants.g  # 9.80665 m/s²

# Side-view camera: looks from +y; sensor +x → lab +x; sensor +y → lab +z.
# Falling atoms (−z) appear in the −y direction on the sensor.
SIDE_VIEW_CAM = CameraGeometry(
    optical_axis=np.array([0.0, 1.0, 0.0]),
    sensor_x_axis=np.array([1.0, 0.0, 0.0]),
    sensor_y_axis=np.array([0.0, 0.0, 1.0]),
    centre_pixel=CENTRE_PIXEL,
    pixel_size_m=PIXEL_SIZE_M,
    magnification=MAGNIFICATION,
)

SIDE_VIEW_CFG = BallisticConfig(
    mass_kg=SR87_MASS_KG,
    gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
    clock_beam_direction=np.array([0.0, 0.0, 1.0]),
    clock_wavelength_m=CLOCK_WAVELENGTH_M,
    camera=SIDE_VIEW_CAM,
)


def _scale() -> float:
    """Pixel scale: metres → pixels."""
    return MAGNIFICATION / PIXEL_SIZE_M


def _free_fall_y(t_s: float) -> float:
    """Expected sensor y of an unkicked cloud at time t (side-view camera)."""
    return CENTRE_PIXEL[1] - 0.5 * GRAVITY * t_s * t_s * _scale()


def pulse_event(
    t_start_s: float,
    is_up: bool,
    duration_s: float = 55e-6,
    state_effect: int = pulse_intent.StateEffect.FLIP,
    addressed_state: int = pulse_intent.AddressedState.AUTO,
    addressed_m: int = pulse_intent.M_AUTO,
    delta_m: "int | None" = None,
) -> IntentEvent:
    """An intent entry as register_pulse records it (defaults = pi transfer)."""
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kind=pulse_intent.Kind.PULSE,
        state_effect=state_effect,
        addressed_state=addressed_state,
        addressed_m=addressed_m,
        delta_m=delta_m if delta_m is not None else (1 if is_up else -1),
    )


def clearout_event(t_start_s: float, duration_s: float = 50e-6) -> IntentEvent:
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kind=pulse_intent.Kind.CLEAROUT,
        state_effect=pulse_intent.StateEffect.NONE,
        addressed_state=pulse_intent.AddressedState.GROUND,
        addressed_m=pulse_intent.M_AUTO,
        delta_m=0,
    )


V_R = recoil_velocity(SIDE_VIEW_CFG)


# ── CameraGeometry (Gram-Schmidt) ─────────────────────────────────────────────


def test_geometry_orthonormalises_hand_entered_tilts():
    """Near-miss axes (operator tilt tweaks) are normalised, not rejected."""
    cam = CameraGeometry(
        optical_axis=np.array([0.02, 0.999, 0.0]),  # slightly tilted, not unit
        sensor_x_axis=np.array([1.0, 0.01, 0.0]),  # not orthogonal to optical
        sensor_y_axis=np.array([0.0, 0.01, 1.01]),
        centre_pixel=CENTRE_PIXEL,
        pixel_size_m=PIXEL_SIZE_M,
    )
    for v in (cam.optical_axis, cam.sensor_x_axis, cam.sensor_y_axis):
        assert np.isclose(np.linalg.norm(v), 1.0)
    assert np.isclose(np.dot(cam.optical_axis, cam.sensor_x_axis), 0.0, atol=1e-12)
    assert np.isclose(np.dot(cam.optical_axis, cam.sensor_y_axis), 0.0, atol=1e-12)
    assert np.isclose(np.dot(cam.sensor_x_axis, cam.sensor_y_axis), 0.0, atol=1e-12)


def test_geometry_rejects_zero_axis():
    with pytest.raises(ValueError, match="non-zero"):
        CameraGeometry(
            optical_axis=np.zeros(3),
            sensor_x_axis=np.array([1.0, 0.0, 0.0]),
            sensor_y_axis=np.array([0.0, 0.0, 1.0]),
            centre_pixel=CENTRE_PIXEL,
            pixel_size_m=PIXEL_SIZE_M,
        )


def test_geometry_rejects_parallel_sensor_axis():
    """A sensor axis parallel to the optical axis is degenerate, not fixable."""
    with pytest.raises(ValueError):
        CameraGeometry(
            optical_axis=np.array([0.0, 1.0, 0.0]),
            sensor_x_axis=np.array([0.0, 1.0, 0.0]),
            sensor_y_axis=np.array([0.0, 0.0, 1.0]),
            centre_pixel=CENTRE_PIXEL,
            pixel_size_m=PIXEL_SIZE_M,
        )


# ── Free fall ─────────────────────────────────────────────────────────────────


def test_free_fall_both_ports():
    """Empty intent stream: both ports on the gravity parabola.

    10 ms of free fall is ½g t² ≈ 0.49 mm ≈ 30.6 px downwards on the sensor.
    """
    t = 10e-3
    out = predict_port_pixels([], t, t, SIDE_VIEW_CFG)
    for port in ("ground", "excited"):
        assert np.isclose(out[port].x_pixel, CENTRE_PIXEL[0])
        assert np.isclose(out[port].y_pixel, _free_fall_y(t))
    # The single initial branch is in the ground state
    assert out["ground"].multiplicity == 1
    assert out["excited"].multiplicity == 0
    # Sanity: the displacement really is ~30.6 px
    assert np.isclose(CENTRE_PIXEL[1] - out["ground"].y_pixel, 30.65, atol=0.1)


def test_free_fall_different_image_times():
    """The two FK shots are at different times: each port falls accordingly."""
    t1, t2 = 10e-3, 13.5e-3
    out = predict_port_pixels([], t1, t2, SIDE_VIEW_CFG)
    assert np.isclose(out["ground"].y_pixel, _free_fall_y(t1))
    assert np.isclose(out["excited"].y_pixel, _free_fall_y(t2))


# ── Single pulses ─────────────────────────────────────────────────────────────


def test_single_up_pulse_kicks_excited_port_up():
    """An up pi pulse transfers the cloud to the excited port with +1 recoil
    from the pulse centre onwards."""
    t_pulse, duration, t_img = 2e-3, 380e-6, 15e-3
    t_centre = t_pulse + duration / 2
    out = predict_port_pixels(
        [pulse_event(t_pulse, is_up=True, duration_s=duration)],
        t_img,
        t_img,
        SIDE_VIEW_CFG,
    )
    expected = _free_fall_y(t_img) + V_R * (t_img - t_centre) * _scale()
    assert np.isclose(out["excited"].y_pixel, expected)
    assert out["excited"].multiplicity == 1
    # Walker carries no lagging branch after a pi intent: the empty ground
    # port points at the only real cloud.
    assert out["ground"].multiplicity == 0
    assert np.isclose(out["ground"].y_pixel, expected)
    # The kick is ≥ 4 px at these timings (validation sanity number)
    assert V_R * (t_img - t_centre) * _scale() > 4.0


def test_single_down_pulse_kicks_down():
    """A down-beam pulse from the ground state kicks −1 recoil."""
    t_pulse, t_img = 2e-3, 15e-3
    duration = 68e-6
    t_centre = t_pulse + duration / 2
    out = predict_port_pixels(
        [pulse_event(t_pulse, is_up=False, duration_s=duration)],
        t_img,
        t_img,
        SIDE_VIEW_CFG,
    )
    expected = _free_fall_y(t_img) - V_R * (t_img - t_centre) * _scale()
    assert np.isclose(out["excited"].y_pixel, expected)


def test_kick_scales_with_pulse_centre_time():
    """Moving the pulse later reduces the displacement proportionally."""
    t_img = 20e-3
    displacements = []
    for t_pulse in (2e-3, 8e-3):
        out = predict_port_pixels(
            [pulse_event(t_pulse, is_up=True, duration_s=100e-6)],
            t_img,
            t_img,
            SIDE_VIEW_CFG,
        )
        displacements.append(out["excited"].y_pixel - _free_fall_y(t_img))
    t_c1, t_c2 = 2e-3 + 50e-6, 8e-3 + 50e-6
    assert np.isclose(
        displacements[0] / displacements[1], (t_img - t_c1) / (t_img - t_c2)
    )


def test_pulse_after_image_time_ignored():
    out = predict_port_pixels(
        [pulse_event(12e-3, is_up=True)], 10e-3, 10e-3, SIDE_VIEW_CFG
    )
    assert np.isclose(out["ground"].y_pixel, _free_fall_y(10e-3))
    assert out["ground"].multiplicity == 1


# ── Slice → clearout → spectroscopy ──────────────────────────────────────────


def test_slice_clearout_spec_ports():
    """Velocity slice (up pi), clearout, then a spectroscopy pulse declared as
    a split (superpose): the ground port holds the transferred atoms (+1 then
    −1 recoil), the excited port the un-transferred slice (+1 recoil)."""
    t_slice, d_slice = 0.5e-3, 380e-6
    t_spec, d_spec = 3e-3, 55e-6
    t_img = 15e-3
    tc_slice = t_slice + d_slice / 2
    tc_spec = t_spec + d_spec / 2

    events = [
        pulse_event(t_slice, is_up=True, duration_s=d_slice),
        clearout_event(t_slice + d_slice + 100e-6),
        pulse_event(
            t_spec,
            is_up=True,
            duration_s=d_spec,
            state_effect=pulse_intent.StateEffect.SUPERPOSE,
        ),
    ]
    out = predict_port_pixels(events, t_img, t_img, SIDE_VIEW_CFG)

    # Excited port: the slice kick only
    y_excited = _free_fall_y(t_img) + V_R * (t_img - tc_slice) * _scale()
    assert np.isclose(out["excited"].y_pixel, y_excited)
    assert out["excited"].multiplicity == 1

    # Ground port: +1 recoil from the slice, −1 from the spec transfer
    y_ground = (
        _free_fall_y(t_img)
        + V_R * (t_img - tc_slice) * _scale()
        - V_R * (t_img - tc_spec) * _scale()
    )
    assert np.isclose(out["ground"].y_pixel, y_ground)
    assert out["ground"].multiplicity == 1


def test_clearout_removes_ground_branch():
    """A clearout right after a superpose pulse leaves only the excited
    branch."""
    events = [
        pulse_event(1e-3, is_up=True, state_effect=pulse_intent.StateEffect.SUPERPOSE),
        clearout_event(2e-3),
    ]
    branches = walk_intent_events(events, 5e-3, SIDE_VIEW_CFG)
    assert len(branches) == 1
    assert not branches[0].is_ground
    assert branches[0].m == 1


# ── Launch ladders ────────────────────────────────────────────────────────────


def _ladder_events(t_slice, d_slice, t_first, spacing, n, duration=55e-6):
    """Slice + clearout + alternating-beam ladder, as the declarative engine
    would record it (explicit intent: each pulse addresses the followed
    branch's pair and transfers +1 recoil)."""
    events = [
        pulse_event(t_slice, is_up=True, duration_s=d_slice),
        clearout_event(t_slice + d_slice + 50e-6),
    ]
    # After the slice the cloud is |e, 1>. Ladder pulse j addresses m = 1 + j,
    # beams alternating starting DOWN (down beam couples |g, m_g> <-> |e, m_g - 1>).
    state_is_ground = False
    m = 1
    for j in range(n):
        is_up = j % 2 == 1
        delta = 1 if is_up else -1
        events.append(
            pulse_event(
                t_first + j * spacing,
                is_up=is_up,
                duration_s=duration,
                addressed_state=(
                    pulse_intent.AddressedState.GROUND
                    if state_is_ground
                    else pulse_intent.AddressedState.EXCITED
                ),
                addressed_m=m,
                delta_m=delta,
            )
        )
        # Followed branch: transfer across the pair gains +1 recoil each time
        m += delta if state_is_ground else -delta
        state_is_ground = not state_is_ground
    return events, m, state_is_ground


@pytest.mark.parametrize("n", [2, 4, 8])
def test_launch_ladder_accumulates_one_recoil_per_pulse(n):
    t_slice, d_slice = 0.5e-3, 380e-6
    t_first, spacing, duration = 2e-3, 200e-6, 55e-6
    t_img = 20e-3

    events, m_final, final_is_ground = _ladder_events(
        t_slice, d_slice, t_first, spacing, n, duration
    )
    assert m_final == 1 + n  # one recoil per pulse, slice included

    out = predict_port_pixels(events, t_img, t_img, SIDE_VIEW_CFG)

    # Expected displacement: sum over kicks of v_r * (t_img - t_centre)
    kick_centres = [t_slice + d_slice / 2] + [
        t_first + j * spacing + duration / 2 for j in range(n)
    ]
    y_expected = _free_fall_y(t_img) + sum(
        V_R * (t_img - tc) * _scale() for tc in kick_centres
    )

    followed_port = "ground" if final_is_ground else "excited"
    other_port = "excited" if final_is_ground else "ground"
    assert np.isclose(out[followed_port].y_pixel, y_expected)
    assert out[followed_port].multiplicity == 1
    # The lagging port is empty in the walker and points at the real cloud
    assert out[other_port].multiplicity == 0
    assert np.isclose(out[other_port].y_pixel, y_expected)


# ── Splits / multi-branch ports ───────────────────────────────────────────────


def test_double_split_flags_multiplicity():
    """Two superpose pulses leave two ground branches: flagged, mean position."""
    t1, t2, t_img = 1e-3, 3e-3, 15e-3
    d = 55e-6
    events = [
        pulse_event(
            t1,
            is_up=True,
            state_effect=pulse_intent.StateEffect.SUPERPOSE,
            duration_s=d,
        ),
        pulse_event(
            t2,
            is_up=True,
            state_effect=pulse_intent.StateEffect.SUPERPOSE,
            duration_s=d,
        ),
    ]
    out = predict_port_pixels(events, t_img, t_img, SIDE_VIEW_CFG)
    # Branches: g0 (never moved), g0+kick1-kick2... walk it: after pulse 1:
    # (g,0), (e,1). Pulse 2 (AUTO addressing) splits both:
    # (g,0), (e,1) from the first; (e,1), (g,0) from the second branch's split
    # — ground port = two branches at m=0 with different histories.
    assert out["ground"].multiplicity == 2
    assert out["excited"].multiplicity == 2


def test_flattened_callback_flip_action_transfers_with_delta_m():
    """A callback flattens to ordinary ``Kind.PULSE`` rows. A FLIP action with
    delta_m=2 transfers the single ground branch to the excited port two recoils
    up at its centre time - exactly as the equivalent ordinary pulse row would."""
    t_cb, d_cb, t_img = 2e-3, 200e-6, 15e-3
    tc = t_cb + d_cb / 2
    events = [
        IntentEvent(
            t_start_s=t_cb,
            duration_s=d_cb,
            kind=pulse_intent.Kind.PULSE,
            state_effect=pulse_intent.StateEffect.FLIP,
            addressed_state=pulse_intent.AddressedState.GROUND,
            addressed_m=0,
            delta_m=2,
        )
    ]
    out = predict_port_pixels(events, t_img, t_img, SIDE_VIEW_CFG)
    expected = _free_fall_y(t_img) + 2 * V_R * (t_img - tc) * _scale()
    assert np.isclose(out["excited"].y_pixel, expected)
    assert out["excited"].multiplicity == 1
    assert out["ground"].multiplicity == 0


def test_flattened_callback_none_action_is_pure_kick():
    """A NONE action is a pure momentum kick on the single declared population:
    the addressed ground branch gains delta_m recoils with its internal state
    unchanged (stays in the ground port)."""
    t_cb, d_cb, t_img = 2e-3, 200e-6, 15e-3
    tc = t_cb + d_cb / 2
    events = [
        IntentEvent(
            t_start_s=t_cb,
            duration_s=d_cb,
            kind=pulse_intent.Kind.PULSE,
            state_effect=pulse_intent.StateEffect.NONE,
            addressed_state=pulse_intent.AddressedState.GROUND,
            addressed_m=0,
            delta_m=2,
        )
    ]
    out = predict_port_pixels(events, t_img, t_img, SIDE_VIEW_CFG)
    expected = _free_fall_y(t_img) + 2 * V_R * (t_img - tc) * _scale()
    assert np.isclose(out["ground"].y_pixel, expected)
    assert out["ground"].multiplicity == 1
    assert out["excited"].multiplicity == 0


# ── Error handling and decoding ───────────────────────────────────────────────


def test_events_must_be_time_ordered():
    events = [
        pulse_event(5e-3, is_up=True),
        pulse_event(1e-3, is_up=True),
    ]
    with pytest.raises(ValueError, match="time-ordered"):
        predict_port_pixels(events, 10e-3, 10e-3, SIDE_VIEW_CFG)


def test_unaddressed_pulse_warns_and_is_skipped(caplog):
    """A pulse declaring a pair with no populated branch is skipped loudly."""
    events = [
        pulse_event(
            1e-3,
            is_up=True,
            addressed_state=pulse_intent.AddressedState.EXCITED,
            addressed_m=5,
        )
    ]
    with caplog.at_level("WARNING"):
        out = predict_port_pixels(events, 10e-3, 10e-3, SIDE_VIEW_CFG)
    assert "no populated branch" in caplog.text
    assert np.isclose(out["ground"].y_pixel, _free_fall_y(10e-3))


def test_intent_event_validation():
    # The enum constructors validate: an unknown code raises ValueError naming
    # the offending enum (e.g. "99 is not a valid Kind").
    with pytest.raises(ValueError, match="Kind"):
        IntentEvent(
            0.0,
            1e-6,
            kind=99,
            state_effect=0,
            addressed_state=-1,
            addressed_m=0,
            delta_m=0,
        )
    with pytest.raises(ValueError, match="StateEffect"):
        IntentEvent(
            0.0,
            1e-6,
            kind=0,
            state_effect=99,
            addressed_state=-1,
            addressed_m=0,
            delta_m=0,
        )


def test_intent_events_from_arrays_roundtrip_and_validation():
    events = intent_events_from_arrays(
        t_start_s=[1e-3, 2e-3],
        duration_s=[55e-6, 50e-6],
        kinds=[pulse_intent.Kind.PULSE, pulse_intent.Kind.CLEAROUT],
        state_effects=[pulse_intent.StateEffect.FLIP, pulse_intent.StateEffect.NONE],
        addressed_states=[
            pulse_intent.AddressedState.AUTO,
            pulse_intent.AddressedState.GROUND,
        ],
        addressed_m=[pulse_intent.M_AUTO, pulse_intent.M_AUTO],
        delta_m=[1, 0],
    )
    assert len(events) == 2
    assert events[0].kind == pulse_intent.Kind.PULSE
    assert np.isclose(events[0].t_centre_s, 1e-3 + 27.5e-6)

    with pytest.raises(ValueError, match="equal lengths"):
        intent_events_from_arrays(
            t_start_s=[0.0],
            duration_s=[],
            kinds=[0],
            state_effects=[0],
            addressed_states=[-1],
            addressed_m=[0],
            delta_m=[0],
        )


def test_rebase_record_times_mu():
    """Recorded (recording-relative) times rebased to seconds since release."""
    ref_period = 1e-9
    # Release at 1_000_000 mu, playback starts at 5_000_000 mu (live timeline);
    # a pulse recorded 2_000_000 mu into the recording fires at
    # 7_000_000 mu live = 6 ms... (6_000_000 mu = 6 ms after release at 1e-9)
    out = rebase_record_times_mu(
        [2_000_000],
        t_playback_start_mu=5_000_000,
        t_release_mu=1_000_000,
        ref_period_s=ref_period,
    )
    assert np.isclose(out[0], 6_000_000 * ref_period)
