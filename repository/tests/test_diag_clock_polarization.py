"""Host-side tests for the clock-polarization diagnostic (PR #37).

These exercise the pure-maths parts of ``diag_clock_polarization`` that do NOT
need the ARTIQ core device:

* the fixed-magnitude in-plane field-rotation map (angle -> coil currents), via the
  module-level nominal constants - checks that ``theta=0`` reproduces the nominal
  field and that ``|B|`` is conserved across the scan (the whole point of rotating
  at fixed magnitude: the Zeeman shift, hence the resonance, stays put);
* the harmonic polarization-axis / contrast estimator used by the
  ``CustomAnalysis`` that writes ``polarization_axis_deg`` /
  ``polarization_contrast`` to the dataset - checks it recovers a known injected
  axis on synthetic ``cos^2`` data with the correct 180-deg periodicity.

The estimator is reimplemented here from the diagnostic's documented formula and
checked to be self-consistent; if the diagnostic's formula changes, update this in
lockstep. (The closure itself is not importable in isolation, so we test the
algorithm it implements.)
"""

import math

import numpy as np
import pytest

from repository.diagnostics import diag_clock_polarization as dcp
from repository.lib import constants


def _polarization_axis_and_contrast(angles_deg, exc):
    """Reimplementation of the diagnostic's harmonic axis/contrast estimator.

    Mirrors ``_analyse_polarization`` in ``diag_clock_polarization``:
        axis = 1/2 * atan2(sum E*sin2theta, sum E*cos2theta)   (mod 180 deg)
        contrast = (Emax - Emin) / (Emax + Emin)
    """
    theta = np.deg2rad(np.asarray(angles_deg, dtype=float))
    e = np.asarray(exc, dtype=float)
    c = float(np.sum(e * np.cos(2.0 * theta)))
    s = float(np.sum(e * np.sin(2.0 * theta)))
    axis_deg = math.degrees(0.5 * math.atan2(s, c)) % 180.0
    span = float(e.max() + e.min())
    contrast = float(e.max() - e.min()) / span if span > 0 else 0.0
    return axis_deg, contrast


# --- field-rotation map (fixed |B|, theta=0 -> nominal) ----------------------


def _currents_for_added_angle(added_angle_rad):
    """Host mirror of the diagnostic's ``_set_rotated_field`` current maths."""
    angle = dcp._XY_ANGLE_0 + added_angle_rad
    bx = dcp._XY_FIELD_MAG * math.cos(angle)
    by = dcp._XY_FIELD_MAG * math.sin(angle)
    ix = bx / dcp._SENS_X
    iy = by / dcp._SENS_Y
    return constants.add_field_offset(ix, iy, 0.0)


def test_theta0_reproduces_nominal_field():
    """At theta=0 the applied (x, y, z) currents equal the nominal clock field."""
    x, y, z = _currents_for_added_angle(0.0)
    nominal = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END
    assert x == pytest.approx(nominal[0], abs=1e-9)
    assert y == pytest.approx(nominal[1], abs=1e-9)
    # z is held at the pure Earth-compensation value (physical z = 0).
    assert z == pytest.approx(constants.FIELD_COMP_Z, abs=1e-9)


def test_field_magnitude_conserved_across_rotation():
    """|B| in the x-y plane is invariant under the scanned rotation angle."""
    mags = []
    for deg in np.linspace(0.0, 360.0, 13):
        x, y, _z = _currents_for_added_angle(math.radians(deg))
        # Back out the physical (Earth-comp-removed) currents, then to Gauss.
        px, py, _pz = constants.calc_new_field_defaults(x, y, 0.0)
        bx = px * dcp._SENS_X
        by = py * dcp._SENS_Y
        mags.append(math.hypot(bx, by))
    assert np.allclose(mags, dcp._XY_FIELD_MAG, rtol=1e-9, atol=1e-12)


def test_nominal_field_is_along_x():
    """The physical nominal field is essentially purely along x (geometry premise)."""
    assert dcp._PHYS_Y_NOMINAL == pytest.approx(0.0, abs=1e-9)
    assert abs(dcp._PHYS_X_NOMINAL) > 0.5  # ~ -1.12 A


# --- harmonic polarization-axis estimator ------------------------------------


@pytest.mark.parametrize("true_axis_deg", [0.0, 30.0, 75.0, 135.0, 179.0])
def test_axis_estimator_recovers_injected_axis(true_axis_deg):
    """cos^2(theta - axis) data -> estimator returns the injected axis (mod 180)."""
    angles = np.linspace(0.0, 360.0, 73)  # 5-deg steps, full turn
    exc = 0.1 + 0.8 * np.cos(np.deg2rad(angles - true_axis_deg)) ** 2
    est_axis, contrast = _polarization_axis_and_contrast(angles, exc)
    # mod-180 circular distance
    d = abs((est_axis - true_axis_deg + 90.0) % 180.0 - 90.0)
    assert d < 2.0, f"axis off: est {est_axis:.1f} vs true {true_axis_deg:.1f}"
    assert 0.0 < contrast <= 1.0


def test_axis_estimator_180_periodicity():
    """Axes 180 deg apart are indistinguishable (the estimator is mod 180)."""
    angles = np.linspace(0.0, 360.0, 73)
    e0 = 0.1 + 0.8 * np.cos(np.deg2rad(angles - 40.0)) ** 2
    e1 = 0.1 + 0.8 * np.cos(np.deg2rad(angles - 220.0)) ** 2
    a0, _ = _polarization_axis_and_contrast(angles, e0)
    a1, _ = _polarization_axis_and_contrast(angles, e1)
    d = abs((a0 - a1 + 90.0) % 180.0 - 90.0)
    assert d < 1e-6


def test_contrast_zero_for_flat_signal():
    angles = np.linspace(0.0, 360.0, 73)
    exc = np.full_like(angles, 0.5)
    _axis, contrast = _polarization_axis_and_contrast(angles, exc)
    assert contrast == pytest.approx(0.0, abs=1e-9)
