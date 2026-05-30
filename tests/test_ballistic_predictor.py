"""
Unit tests for repository.lib.physics.ballistic.

All tests are pure Python/NumPy — no ARTIQ fixtures required.
"""

import numpy as np
import pytest
import scipy.constants

from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.ballistic import predict_position
from repository.lib.physics.ballistic import predict_positions_from_mu
from repository.lib.physics.ballistic import recoil_velocity

pytestmark = pytest.mark.xfail(
    reason="Ballistic predictor not implemented yet", raises=NotImplementedError
)


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

# Bottom-up camera: looks upward (+z optical axis); sensor axes in lab x-y plane.
BOTTOM_UP_CAM = CameraGeometry(
    optical_axis=np.array([0.0, 0.0, 1.0]),
    sensor_x_axis=np.array([1.0, 0.0, 0.0]),
    sensor_y_axis=np.array([0.0, 1.0, 0.0]),
    centre_pixel=CENTRE_PIXEL,
    pixel_size_m=PIXEL_SIZE_M,
    magnification=MAGNIFICATION,
)

BOTTOM_UP_CFG = BallisticConfig(
    mass_kg=SR87_MASS_KG,
    gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
    clock_beam_direction=np.array([0.0, 0.0, 1.0]),
    clock_wavelength_m=CLOCK_WAVELENGTH_M,
    camera=BOTTOM_UP_CAM,
)


def _scale() -> float:
    """Pixel scale: metres → pixels."""
    return MAGNIFICATION / PIXEL_SIZE_M


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_free_fall_side_view():
    """After 10 ms free fall, sensor y changes by −½g t² * scale; x unchanged."""
    t = 10e-3
    x_pix, y_pix = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    expected_dy = -0.5 * GRAVITY * t**2 * _scale()
    assert x_pix == pytest.approx(CENTRE_PIXEL[0], abs=1e-9)
    assert y_pix == pytest.approx(CENTRE_PIXEL[1] + expected_dy, rel=1e-6)


def test_zero_time_returns_centre():
    """At t=0 the prediction must equal the trap centre pixel regardless of state."""
    for state in ("ground", "excited"):
        x_pix, y_pix = predict_position(
            site_offset_m=np.zeros(3),
            initial_velocity_m_per_s=np.zeros(3),
            pulse_times_s=[],
            pulse_is_up=[],
            t_image_s=0.0,
            cfg=SIDE_VIEW_CFG,
            state=state,
        )
        assert x_pix == pytest.approx(CENTRE_PIXEL[0], abs=1e-9)
        assert y_pix == pytest.approx(CENTRE_PIXEL[1], abs=1e-9)


def test_bottom_view_no_apparent_fall():
    """Bottom-up camera: gravity is along the optical axis, so pixel coords are unchanged."""
    t = 50e-3
    x_pix, y_pix = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=BOTTOM_UP_CFG,
        state="ground",
    )
    # Gravity is purely along optical_axis (+z), so both sensor projections = 0.
    assert x_pix == pytest.approx(CENTRE_PIXEL[0], abs=1e-9)
    assert y_pix == pytest.approx(CENTRE_PIXEL[1], abs=1e-9)


def test_out_of_plane_tilt():
    """
    Side camera tilted θ=5° so optical_axis has a −z component.
    The sensor_y_axis is no longer perfectly aligned with lab +z, so
    vertical pixel motion is reduced by cos(θ) compared to the aligned case.
    There should be zero horizontal (x) sensor motion.
    """
    theta = np.radians(5.0)
    # Rotate the side-view camera about lab +x by θ:
    # optical_axis → [0, cos θ, -sin θ] (still points mostly +y)
    # sensor_y_axis → [0, sin θ,  cos θ] (still mostly +z)
    tilted_cam = CameraGeometry(
        optical_axis=np.array([0.0, np.cos(theta), -np.sin(theta)]),
        sensor_x_axis=np.array([1.0, 0.0, 0.0]),
        sensor_y_axis=np.array([0.0, np.sin(theta), np.cos(theta)]),
        centre_pixel=CENTRE_PIXEL,
        pixel_size_m=PIXEL_SIZE_M,
        magnification=MAGNIFICATION,
    )
    tilted_cfg = BallisticConfig(
        mass_kg=SR87_MASS_KG,
        gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
        clock_beam_direction=np.array([0.0, 0.0, 1.0]),
        clock_wavelength_m=CLOCK_WAVELENGTH_M,
        camera=tilted_cam,
    )

    t = 20e-3
    x_pix_tilted, y_pix_tilted = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=tilted_cfg,
        state="ground",
    )
    x_pix_aligned, y_pix_aligned = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )

    # Vertical (y sensor) motion is reduced by cos(θ)
    dy_aligned = y_pix_aligned - CENTRE_PIXEL[1]
    dy_tilted = y_pix_tilted - CENTRE_PIXEL[1]
    assert dy_tilted == pytest.approx(dy_aligned * np.cos(theta), rel=1e-6)

    # No horizontal (x sensor) motion from pure vertical gravity
    assert x_pix_tilted == pytest.approx(CENTRE_PIXEL[0], abs=1e-9)


def test_upward_kick_partially_cancels_gravity():
    """
    is_up=True pulse at t=0 on side-view camera.
    The +z kick means sensor_y increases by +v_r * t, partially offsetting the
    downward free-fall.
    """
    t = 20e-3
    v_r = recoil_velocity(SIDE_VIEW_CFG)

    x_free, y_free = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    x_kick, y_kick = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[0.0],
        pulse_is_up=[True],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="excited",
    )

    expected_dy_kick = v_r * t * _scale()
    assert y_kick == pytest.approx(y_free + expected_dy_kick, rel=1e-6)
    assert x_kick == pytest.approx(x_free, abs=1e-9)


def test_downward_kick_adds_to_fall():
    """
    is_up=False pulse at t=0. The −z kick means sensor_y decreases faster.
    """
    t = 20e-3
    v_r = recoil_velocity(SIDE_VIEW_CFG)

    _, y_free = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    _, y_kick = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[0.0],
        pulse_is_up=[False],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="excited",
    )

    expected_dy_kick = -v_r * t * _scale()
    assert y_kick == pytest.approx(y_free + expected_dy_kick, rel=1e-6)


def test_two_opposite_kicks_leave_position_offset():
    """
    +ℏk at t₁, −ℏk at t₂ (t₂ > t₁). Net Δv = 0, but residual displacement is
    +v_r*(t−t₁) − v_r*(t−t₂) = v_r*(t₂−t₁) along the clock direction.
    """
    t = 30e-3
    t1 = 5e-3
    t2 = 15e-3
    v_r = recoil_velocity(SIDE_VIEW_CFG)

    _, y_pix = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[t1, t2],
        pulse_is_up=[True, False],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="excited",
    )
    _, y_free = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )

    # Residual displacement = v_r * (t2 - t1) along +z → +y_sensor
    expected_dy = v_r * (t2 - t1) * _scale()
    assert y_pix == pytest.approx(y_free + expected_dy, rel=1e-6)


def test_ground_state_ignores_kicks():
    """state='ground' must give the same result regardless of the pulse log."""
    t = 20e-3

    xy_no_pulses = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    xy_with_pulses = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[2e-3, 10e-3, 18e-3],
        pulse_is_up=[True, False, True],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )

    assert xy_no_pulses[0] == pytest.approx(xy_with_pulses[0], abs=1e-9)
    assert xy_no_pulses[1] == pytest.approx(xy_with_pulses[1], abs=1e-9)


def test_recoil_velocity_value():
    """Sr-87 at 698 nm should give v_r ≈ 6.63 mm/s. Check to 0.1 %."""
    v_r = recoil_velocity(SIDE_VIEW_CFG)
    # h / (m * λ):  (6.626e-34) / (87 * 1.66e-27 * 698e-9) ≈ 6.57e-3 m/s
    v_r_hand = scipy.constants.h / (SR87_MASS_KG * CLOCK_WAVELENGTH_M)
    assert v_r == pytest.approx(v_r_hand, rel=1e-3)
    assert 6e-3 < v_r < 7e-3, f"Recoil velocity out of expected range: {v_r:.4f} m/s"


def test_kick_along_optical_axis_invisible():
    """
    When the clock beam is parallel to the optical axis, a kick along that
    direction should NOT change the projected pixel position at all.
    """
    # Clock beam = optical_axis of side-view camera = [0, 1, 0]
    cfg_beam_along_axis = BallisticConfig(
        mass_kg=SR87_MASS_KG,
        gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
        clock_beam_direction=np.array([0.0, 1.0, 0.0]),  # along optical_axis
        clock_wavelength_m=CLOCK_WAVELENGTH_M,
        camera=SIDE_VIEW_CAM,
    )

    t = 20e-3
    xy_no_kick = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=cfg_beam_along_axis,
        state="ground",
    )
    xy_kick = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[5e-3],
        pulse_is_up=[True],
        t_image_s=t,
        cfg=cfg_beam_along_axis,
        state="excited",
    )

    assert xy_kick[0] == pytest.approx(xy_no_kick[0], abs=1e-9)
    assert xy_kick[1] == pytest.approx(xy_no_kick[1], abs=1e-9)


def test_in_plane_drift():
    """
    Non-zero initial velocity in the sensor plane → linear pixel drift.
    Same magnitude along the optical axis → zero pixel drift.
    """
    t = 20e-3
    v_in = 0.01  # 1 cm/s

    # Velocity along sensor_x_axis (lab +x) — should produce linear x-pixel drift
    xy_in_plane = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.array([v_in, 0.0, 0.0]),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    expected_dx = v_in * t * _scale()
    assert xy_in_plane[0] == pytest.approx(CENTRE_PIXEL[0] + expected_dx, rel=1e-6)

    # Velocity along optical_axis (lab +y) — should produce zero pixel drift
    xy_out_of_plane = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.array([0.0, v_in, 0.0]),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=t,
        cfg=SIDE_VIEW_CFG,
        state="ground",
    )
    # Only gravity contributes to y; x unchanged
    assert xy_out_of_plane[0] == pytest.approx(CENTRE_PIXEL[0], abs=1e-9)


def test_mu_wrapper_matches_seconds_version():
    """predict_positions_from_mu must match predict_position for the same scenario."""
    ref_period_s = 1e-9
    t_zero_mu = 1_000_000_000  # 1 second offset (arbitrary)

    t_pulse_start_s = 4e-3
    t_pulse_duration_s = 2e-3
    t_pulse_start_s + t_pulse_duration_s / 2
    t_img1_s = 20e-3
    t_img2_s = 23e-3

    pulse_start_mu = np.array(
        [t_zero_mu + round(t_pulse_start_s / ref_period_s)], dtype=np.int64
    )
    pulse_duration_mu = np.array(
        [round(t_pulse_duration_s / ref_period_s)], dtype=np.int64
    )
    pulse_up = np.array([True])
    img_mu = np.array(
        [
            t_zero_mu + round(t_img1_s / ref_period_s),
            t_zero_mu + round(t_img2_s / ref_period_s),
        ],
        dtype=np.int64,
    )

    out = predict_positions_from_mu(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_start_times_mu=pulse_start_mu,
        pulse_durations_mu=pulse_duration_mu,
        pulse_is_up=pulse_up,
        image_times_mu=img_mu,
        t_zero_mu=t_zero_mu,
        ref_period_s=ref_period_s,
        cfg=SIDE_VIEW_CFG,
    )

    for i, (t_img_s, state) in enumerate(
        [(t_img1_s, "ground"), (t_img1_s, "excited"), (t_img2_s, "excited")]
    ):
        if state == "ground":
            xy_ref = predict_position(
                np.zeros(3),
                np.zeros(3),
                [t_pulse_start_s],
                [True],
                t_img_s,
                SIDE_VIEW_CFG,
                "ground",
                pulse_durations_s=[t_pulse_duration_s],
            )
            assert out["ground"][0, 0] == pytest.approx(xy_ref[0], rel=1e-6)
            assert out["ground"][0, 1] == pytest.approx(xy_ref[1], rel=1e-6)
        elif i == 1:
            xy_ref = predict_position(
                np.zeros(3),
                np.zeros(3),
                [t_pulse_start_s],
                [True],
                t_img_s,
                SIDE_VIEW_CFG,
                "excited",
                pulse_durations_s=[t_pulse_duration_s],
            )
            assert out["excited"][0, 0] == pytest.approx(xy_ref[0], rel=1e-6)
            assert out["excited"][0, 1] == pytest.approx(xy_ref[1], rel=1e-6)
        else:
            xy_ref = predict_position(
                np.zeros(3),
                np.zeros(3),
                [t_pulse_start_s],
                [True],
                t_img2_s,
                SIDE_VIEW_CFG,
                "excited",
                pulse_durations_s=[t_pulse_duration_s],
            )
            assert out["excited"][1, 0] == pytest.approx(xy_ref[0], rel=1e-6)
            assert out["excited"][1, 1] == pytest.approx(xy_ref[1], rel=1e-6)


def test_pulse_duration_shifts_effective_kick_time():
    """Longer duration delays the effective kick when the pulse start time is fixed."""
    t_image_s = 20e-3
    pulse_start_s = 5e-3
    short_duration_s = 0.0
    long_duration_s = 4e-3
    v_r = recoil_velocity(SIDE_VIEW_CFG)

    _, y_short = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[pulse_start_s],
        pulse_is_up=[True],
        t_image_s=t_image_s,
        cfg=SIDE_VIEW_CFG,
        state="excited",
        pulse_durations_s=[short_duration_s],
    )
    _, y_long = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[pulse_start_s],
        pulse_is_up=[True],
        t_image_s=t_image_s,
        cfg=SIDE_VIEW_CFG,
        state="excited",
        pulse_durations_s=[long_duration_s],
    )

    expected_delta = -v_r * ((long_duration_s - short_duration_s) / 2) * _scale()
    assert y_long == pytest.approx(y_short + expected_delta, rel=1e-6)


def test_monotonic_pulse_times_enforced():
    """Non-monotonic pulse_times_s must raise ValueError."""
    with pytest.raises(ValueError, match="monotonically"):
        predict_position(
            site_offset_m=np.zeros(3),
            initial_velocity_m_per_s=np.zeros(3),
            pulse_times_s=[10e-3, 5e-3],  # backwards
            pulse_is_up=[True, True],
            t_image_s=20e-3,
            cfg=SIDE_VIEW_CFG,
            state="excited",
        )


def test_camera_geometry_validates_orthonormal():
    """CameraGeometry must reject non-unit or non-orthogonal axes."""
    # Non-unit optical_axis
    with pytest.raises(ValueError):
        CameraGeometry(
            optical_axis=np.array([0.0, 2.0, 0.0]),  # not unit
            sensor_x_axis=np.array([1.0, 0.0, 0.0]),
            sensor_y_axis=np.array([0.0, 0.0, 1.0]),
            centre_pixel=CENTRE_PIXEL,
            pixel_size_m=PIXEL_SIZE_M,
        )

    # Non-orthogonal axes
    with pytest.raises(ValueError):
        CameraGeometry(
            optical_axis=np.array([0.0, 1.0, 0.0]),
            sensor_x_axis=np.array([1.0, 0.0, 0.0]),
            sensor_y_axis=np.array([0.5, 0.5, 1.0 / np.sqrt(2)]),  # not orthogonal to x
            centre_pixel=CENTRE_PIXEL,
            pixel_size_m=PIXEL_SIZE_M,
        )
