"""Host-side test for the slice-time consumer contract. Calibration fragment
build/compile is covered separately by test_calibration_kernels."""

import numpy as np


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
    from qbutler.optimizers import ParamSpec
    from repository.lib.calibrations.rabi_pi_time import _make_rabi_flop_optimizer

    nominal = 56e-6
    opt = _make_rabi_flop_optimizer(nominal)

    def run(true_pi):
        spec = ParamSpec(name="pi_time", min=1e-6, max=2.5 * nominal, handle=None)
        gen = opt([spec])
        params = next(gen)
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
    from qbutler.optimizers import ParamSpec
    from repository.lib.calibrations.coarse_clock_centre import (
        _NOMINAL_DELIVERY_FREQUENCY,
    )
    from repository.lib.calibrations.coarse_clock_centre import _SEARCH_HALF_SPAN
    from repository.lib.calibrations.coarse_clock_centre import _coarse_fit_optimizer

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


def _run_delivery_optimizer(spec, true_centre, width=3e3):
    """Drive _delivery_fit_optimizer against an ideal Gaussian line."""
    from repository.lib.calibrations.clock_delivery import _delivery_fit_optimizer

    gen = _delivery_fit_optimizer([spec])
    params = next(gen)
    sweep_points = []
    try:
        while True:
            f = params["delivery_frequency"]
            sweep_points.append(f)
            excitation = np.exp(-((f - true_centre) ** 2) / (2 * width**2))
            params = gen.send((0, excitation))  # 0 == CalibrationResult.OK
    except StopIteration as e:
        return e.value, sweep_points


def test_delivery_optimizer_single_sweep_when_centred():
    from qbutler.optimizers import ParamSpec
    from repository.lib.calibrations.clock_delivery import _SWEEP_POINTS

    centre = 99.44e6
    spec = ParamSpec(
        name="delivery_frequency", min=centre - 30e3, max=centre + 30e3, handle=None
    )
    best, sweep = _run_delivery_optimizer(spec, true_centre=centre + 5e3)
    assert best is not None
    assert abs(best["delivery_frequency"] - (centre + 5e3)) < 1e3
    assert len(sweep) == _SWEEP_POINTS  # in-window centre: no rewiden


def test_delivery_optimizer_edge_guard_rewidens_on_misseeded_window():
    from qbutler.optimizers import ParamSpec
    from repository.lib.calibrations.clock_delivery import _SWEEP_POINTS

    # The true line sits at the window edge (e.g. a stale cross-beam offset):
    # the guard must recentre + double the window and find it on the rerun.
    centre = 99.44e6
    true_centre = centre + 28e3
    spec = ParamSpec(
        name="delivery_frequency", min=centre - 30e3, max=centre + 30e3, handle=None
    )
    best, sweep = _run_delivery_optimizer(spec, true_centre=true_centre)
    assert best is not None
    assert len(sweep) == 2 * _SWEEP_POINTS  # rewidened once
    assert abs(best["delivery_frequency"] - true_centre) < 1e3
