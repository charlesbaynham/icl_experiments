"""
Ballistic atom trajectory predictor
====================================

Pure host-side (no ARTIQ) 3-D ballistic physics for predicting where an atom
cloud will appear on a camera sensor at a given imaging time.

The module models atoms subject to:
- Gravity (configurable lab-frame vector, default [0, 0, -g]).
- Discrete photon-recoil impulses from clock-light pulses, each contributing
  ±ℏk/m along the configured clock-beam direction.

Projection from 3-D lab coordinates to 2-D sensor pixels uses an orthographic
camera model fully specified by three lab-frame unit vectors.

Usage example::

    from repository.lib import constants
    from repository.lib.physics.ballistic import (
        BallisticConfig, CameraGeometry, predict_position, recoil_velocity
    )

    camera = CameraGeometry(
        optical_axis=constants.ANDOR_OPTICAL_AXIS_DEFAULT,
        sensor_x_axis=constants.ANDOR_SENSOR_X_AXIS_DEFAULT,
        sensor_y_axis=constants.ANDOR_SENSOR_Y_AXIS_DEFAULT,
        centre_pixel=(256.0, 256.0),
        pixel_size_m=constants.ANDOR_CAMERA_FACTS["pixel_size"],
        magnification=constants.ANDOR_CAMERA_FACTS["magnification"],
    )
    cfg = BallisticConfig(
        mass_kg=constants.SR_ATOM_MASS_KG,
        gravity_vec_m_per_s2=constants.GRAVITY_VEC_M_PER_S2,
        clock_beam_direction=constants.CLOCK_UP_BEAM_DIRECTION,
        clock_wavelength_m=constants.CLOCK_WAVELENGTH_M,
        camera=camera,
    )
    x_pix, y_pix = predict_position(
        site_offset_m=np.zeros(3),
        initial_velocity_m_per_s=np.zeros(3),
        pulse_times_s=[],
        pulse_is_up=[],
        t_image_s=10e-3,
        cfg=cfg,
        state="ground",
        pulse_durations_s=[],
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from typing import Sequence

import numpy as np
import scipy.constants


@dataclass(frozen=True)
class CameraGeometry:
    """Orthographic projection from 3-D lab metres to 2-D sensor pixels.

    Three orthonormal lab-frame unit vectors fully specify the camera:

    - ``optical_axis``: unit vector along the camera's optical axis, pointing
      **from the trap toward the camera** (i.e. the inward scene normal).
    - ``sensor_x_axis``: lab-frame direction that maps to +x on the sensor.
    - ``sensor_y_axis``: lab-frame direction that maps to +y on the sensor.

    The trap position at t=0 projects to ``centre_pixel``.
    ``magnification / pixel_size_m`` converts metres → pixels.
    """

    optical_axis: np.ndarray
    sensor_x_axis: np.ndarray
    sensor_y_axis: np.ndarray
    centre_pixel: tuple[float, float]
    pixel_size_m: float
    magnification: float = 1.0

    def __post_init__(self):
        # Normalise and validate each axis
        for name in ("optical_axis", "sensor_x_axis", "sensor_y_axis"):
            v = np.asarray(getattr(self, name), dtype=float)
            norm = np.linalg.norm(v)
            if norm < 1e-10:
                raise ValueError(f"CameraGeometry.{name} must be non-zero")
            if not np.isclose(norm, 1.0, atol=1e-6):
                raise ValueError(
                    f"CameraGeometry.{name} must be a unit vector (|v|={norm:.6f})"
                )
            object.__setattr__(self, name, v)

        oa = self.optical_axis
        sx = self.sensor_x_axis
        sy = self.sensor_y_axis

        if not np.isclose(np.dot(oa, sx), 0.0, atol=1e-6):
            raise ValueError("optical_axis and sensor_x_axis must be orthogonal")
        if not np.isclose(np.dot(oa, sy), 0.0, atol=1e-6):
            raise ValueError("optical_axis and sensor_y_axis must be orthogonal")
        if not np.isclose(np.dot(sx, sy), 0.0, atol=1e-6):
            raise ValueError("sensor_x_axis and sensor_y_axis must be orthogonal")

    def project(self, pos_lab_m: np.ndarray) -> tuple[float, float]:
        """Project a 3-D lab position (metres) onto sensor pixel coordinates."""
        scale = self.magnification / self.pixel_size_m
        cx, cy = self.centre_pixel
        x_pix = cx + np.dot(self.sensor_x_axis, pos_lab_m) * scale
        y_pix = cy + np.dot(self.sensor_y_axis, pos_lab_m) * scale
        return float(x_pix), float(y_pix)


@dataclass(frozen=True)
class BallisticConfig:
    """Physical parameters for the ballistic predictor."""

    mass_kg: float
    gravity_vec_m_per_s2: np.ndarray
    clock_beam_direction: np.ndarray
    clock_wavelength_m: float
    camera: CameraGeometry

    def __post_init__(self):
        object.__setattr__(
            self,
            "gravity_vec_m_per_s2",
            np.asarray(self.gravity_vec_m_per_s2, dtype=float),
        )
        direction = np.asarray(self.clock_beam_direction, dtype=float)
        norm = np.linalg.norm(direction)
        if norm < 1e-10:
            raise ValueError("clock_beam_direction must be non-zero")
        object.__setattr__(self, "clock_beam_direction", direction / norm)


def recoil_velocity(cfg: BallisticConfig) -> float:
    """Single-photon recoil speed: v_r = h / (m * λ)  [m/s]."""
    return scipy.constants.h / (cfg.mass_kg * cfg.clock_wavelength_m)


def predict_position(
    site_offset_m: np.ndarray,
    initial_velocity_m_per_s: np.ndarray,
    pulse_times_s: Sequence[float],
    pulse_is_up: Sequence[bool],
    t_image_s: float,
    cfg: BallisticConfig,
    state: Literal["ground", "excited"],
    pulse_durations_s: Sequence[float] | None = None,
) -> tuple[float, float]:
    """3-D ballistic integration → sensor pixel coordinates.

    t=0 is the moment atoms are released (trap turned off).

    Each clock pulse contributes an instantaneous velocity kick:
        Δv = (+1 if is_up else -1) * v_r * clock_beam_direction

    Pulses are described by their start time and duration. The instantaneous
    kick model applies the kick at ``pulse_times_s[i] + pulse_durations_s[i] / 2``.

    Position at imaging time::

        r(t) = r0 + v0*t + ½·g·t²  +  Σ_{t_i + τ_i/2 ≤ t} Δv_i·(t − (t_i + τ_i/2))

    ``state="ground"`` ignores all kicks; ``state="excited"`` applies them all.

    Returns ``(x_pixel, y_pixel)`` via orthographic projection.
    """
    # FIXME This logic is totally wrong
    pulse_times_s = list(pulse_times_s)
    pulse_is_up = list(pulse_is_up)
    if pulse_durations_s is None:
        pulse_durations_s = [0.0] * len(pulse_times_s)
    pulse_durations_s = list(pulse_durations_s)

    if len(pulse_times_s) != len(pulse_is_up):
        raise ValueError("pulse_times_s and pulse_is_up must have the same length")
    if len(pulse_times_s) != len(pulse_durations_s):
        raise ValueError(
            "pulse_times_s and pulse_durations_s must have the same length"
        )

    if len(pulse_times_s) > 1:
        for i in range(1, len(pulse_times_s)):
            if pulse_times_s[i] < pulse_times_s[i - 1]:
                raise ValueError(
                    f"pulse_times_s must be monotonically non-decreasing "
                    f"(got {pulse_times_s[i-1]} then {pulse_times_s[i]})"
                )

    r0 = np.asarray(site_offset_m, dtype=float)
    v0 = np.asarray(initial_velocity_m_per_s, dtype=float)
    g = cfg.gravity_vec_m_per_s2
    t = t_image_s

    # Free-fall position
    r = r0 + v0 * t + 0.5 * g * t * t

    if state == "excited":
        v_r = recoil_velocity(cfg)
        for start_i, duration_i, up_i in zip(
            pulse_times_s, pulse_durations_s, pulse_is_up
        ):
            t_i = start_i + duration_i / 2
            if t_i <= t:
                sign = 1.0 if up_i else -1.0
                delta_v = sign * v_r * cfg.clock_beam_direction
                r = r + delta_v * (t - t_i)
    elif state != "ground":
        raise ValueError(f"state must be 'ground' or 'excited', got {state!r}")

    return cfg.camera.project(r)


def predict_positions_from_mu(
    site_offset_m: np.ndarray,
    initial_velocity_m_per_s: np.ndarray,
    pulse_start_times_mu: np.ndarray,
    pulse_durations_mu: np.ndarray,
    pulse_is_up: np.ndarray,
    image_times_mu: np.ndarray,
    t_zero_mu: int,
    ref_period_s: float,
    cfg: BallisticConfig,
) -> dict[str, np.ndarray]:
    """RPC-friendly wrapper converting machine units → seconds then calling predict_position.

    Parameters
    ----------
    pulse_start_times_mu:
        1-D int64 array of pulse start timestamps in ARTIQ machine units.
    pulse_durations_mu:
        1-D int64 array of pulse durations in ARTIQ machine units.
    pulse_is_up:
        1-D bool array, same length as pulse_start_times_mu.
    image_times_mu:
        1-D int64 array of N imaging timestamps in machine units.
    t_zero_mu:
        Machine-unit timestamp of atom release (t=0 for the predictor).
    ref_period_s:
        ARTIQ core reference period in seconds (``core.ref_period``, typically 1e-9).

    Returns
    -------
    dict with keys ``"ground"`` and ``"excited"``, each an (N, 2) float64 array
    of (x_pixel, y_pixel) coordinates.
    """
    pulse_times_s = (
        np.asarray(pulse_start_times_mu, dtype=np.int64) - t_zero_mu
    ) * ref_period_s
    pulse_durations_s = np.asarray(pulse_durations_mu, dtype=np.int64) * ref_period_s
    pulse_is_up_list = list(bool(v) for v in pulse_is_up)
    image_times_s = (
        np.asarray(image_times_mu, dtype=np.int64) - t_zero_mu
    ) * ref_period_s

    n = len(image_times_s)
    ground_pix = np.empty((n, 2), dtype=float)
    excited_pix = np.empty((n, 2), dtype=float)

    for i, t_img in enumerate(image_times_s):
        ground_pix[i] = predict_position(
            site_offset_m=site_offset_m,
            initial_velocity_m_per_s=initial_velocity_m_per_s,
            pulse_times_s=pulse_times_s,
            pulse_is_up=pulse_is_up_list,
            t_image_s=float(t_img),
            cfg=cfg,
            state="ground",
            pulse_durations_s=pulse_durations_s,
        )
        excited_pix[i] = predict_position(
            site_offset_m=site_offset_m,
            initial_velocity_m_per_s=initial_velocity_m_per_s,
            pulse_times_s=pulse_times_s,
            pulse_is_up=pulse_is_up_list,
            t_image_s=float(t_img),
            cfg=cfg,
            state="excited",
            pulse_durations_s=pulse_durations_s,
        )

    return {"ground": ground_pix, "excited": excited_pix}
