"""
Ballistic-predictor geometry and physical configuration
=======================================================

Pure host-side (no ARTIQ) building blocks for predicting where an atom cloud
appears on a camera sensor: an orthographic camera model
(:class:`CameraGeometry`), the physical parameters
(:class:`BallisticConfig`) and the photon-recoil speed
(:func:`recoil_velocity`).

The trajectory prediction itself - driven by the recorded pulse *intent*
stream - lives in :mod:`repository.lib.physics.trajectory`.

Usage example::

    from repository.lib import constants
    from repository.lib.physics.ballistic import BallisticConfig, CameraGeometry

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
"""

from __future__ import annotations

from dataclasses import dataclass

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
        # Normalise the axes and re-orthogonalise by Gram-Schmidt rather than
        # rejecting near-miss inputs: the axis components are exposed as
        # freely-editable ndscan parameters for small tilt corrections, and a
        # hand-entered tilt (e.g. optical_axis_y = 0.999) must not blow up an
        # experiment mid-shot. Genuinely degenerate inputs still raise.
        def _unit(v: np.ndarray, name: str) -> np.ndarray:
            norm = np.linalg.norm(v)
            if norm < 1e-10:
                raise ValueError(f"CameraGeometry.{name} must be non-zero")
            return v / norm

        oa = _unit(np.asarray(self.optical_axis, dtype=float), "optical_axis")

        sx = np.asarray(self.sensor_x_axis, dtype=float)
        sx = sx - np.dot(sx, oa) * oa
        sx = _unit(sx, "sensor_x_axis (after projecting out the optical axis)")

        sy = np.asarray(self.sensor_y_axis, dtype=float)
        sy = sy - np.dot(sy, oa) * oa - np.dot(sy, sx) * sx
        sy = _unit(sy, "sensor_y_axis (after projecting out the other axes)")

        object.__setattr__(self, "optical_axis", oa)
        object.__setattr__(self, "sensor_x_axis", sx)
        object.__setattr__(self, "sensor_y_axis", sy)

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
