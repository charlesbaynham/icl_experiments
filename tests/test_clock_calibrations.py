"""Host-side tests for the clock calibration helpers (numpy-only fit + the
slice-time consumer contract). Fragment build/compile is covered separately by
test_compile_all."""

import numpy as np

from repository.lib.calibrations._fit_helpers import fit_peak_x


def test_fit_peak_x_locates_subgrid_peak():
    xs = np.arange(0, 6, dtype=float)
    ys = np.exp(-((xs - 2.3) ** 2) / (2 * 0.9**2))
    assert abs(fit_peak_x(xs, ys) - 2.3) < 0.3


def test_fit_peak_x_ignores_nan_shots():
    xs = np.arange(0, 6, dtype=float)
    ys = np.exp(-((xs - 3.0) ** 2) / (2 * 1.0**2))
    ys[3] = np.nan  # zero-atom shot at the true max
    # falls back gracefully to the finite samples, staying in-range
    out = fit_peak_x(xs, ys)
    assert 1.5 < out < 4.5


def test_fit_peak_x_edge_and_empty():
    assert fit_peak_x([0, 1, 2], [5, 1, 0]) == 0.0
    assert fit_peak_x([], []) is None


def test_scaled_clock_slice_time_ratio():
    from repository.lib import constants
    from repository.lib.calibrations.clock_slice_time import scaled_clock_slice_time
    from repository.lib.lmt_sequence import Beam

    # A pi time equal to nominal leaves the slice time unchanged
    for beam, nominal in (
        (Beam.UP, constants.CLOCK_PI_TIME),
        (Beam.DOWN, constants.DOWN_CLOCK_BEAM_PI_TIME),
    ):
        assert np.isclose(
            scaled_clock_slice_time(nominal, beam), constants.CLOCK_SHELVING_PULSE_TIME
        )
        # A 10% longer pi time scales the slice by 10%
        assert np.isclose(
            scaled_clock_slice_time(1.1 * nominal, beam),
            1.1 * constants.CLOCK_SHELVING_PULSE_TIME,
        )


def test_rabi_optimizer_finds_pi_and_gates_band():
    from repository.lib.calibrations.rabi_pi_time import _make_rabi_flop_optimizer
    from qbutler.optimizers import ParamSpec

    nominal = 56e-6
    opt = _make_rabi_flop_optimizer(nominal)

    def run(true_pi):
        spec = ParamSpec(name="pi_time", min=1e-6, max=2.5 * nominal, handle=None)
        gen = opt([spec])
        params = next(gen)
        result = None
        try:
            while True:
                t = params["pi_time"]
                exc = np.sin(np.pi * t / (2 * true_pi)) ** 2  # ideal Rabi flop
                params = gen.send((0, exc))  # 0 == CalibrationResult.OK
        except StopIteration as e:
            return e.value

    got = run(56e-6)
    assert got is not None and abs(got["pi_time"] - 56e-6) < 6e-6  # in-band, near pi
    assert run(120e-6) is None  # first max out of sane band -> not persisted


def test_coarse_optimizer_finds_broad_line_centre():
    from repository.lib.calibrations.coarse_clock_centre import _coarse_fit_optimizer
    from repository.lib.calibrations.coarse_clock_centre import (
        _NOMINAL_DELIVERY_FREQUENCY,
    )
    from repository.lib.calibrations.coarse_clock_centre import _SEARCH_HALF_SPAN
    from qbutler.optimizers import ParamSpec

    true_centre = _NOMINAL_DELIVERY_FREQUENCY + 40e3
    spec = ParamSpec(
        name="delivery_frequency",
        min=_NOMINAL_DELIVERY_FREQUENCY - _SEARCH_HALF_SPAN,
        max=_NOMINAL_DELIVERY_FREQUENCY + _SEARCH_HALF_SPAN,
        handle=None,
    )

    gen = _coarse_fit_optimizer([spec])
    params = next(gen)
    try:
        while True:
            f = params["delivery_frequency"]
            excitation = np.exp(-((f - true_centre) ** 2) / (2 * 30e3**2))
            params = gen.send((0, excitation))  # 0 == CalibrationResult.OK
    except StopIteration as e:
        best = e.value

    assert best is not None
    assert abs(best["delivery_frequency"] - true_centre) < 10e3  # ~one grid step
