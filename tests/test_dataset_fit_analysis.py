"""Host-side checks for ``make_dataset_fit_analysis`` (PR #37).

A diagnostic's dataset-output fit can fail on real data. Concretely, every
diagnostic seeds ``default_num_repeats = 2``, so each scan x-value appears twice;
the frequency-estimating oitg initialisers then compute ``int(.../min_step)``
with ``min_step = 0`` (duplicate adjacent samples), giving ``int(inf)`` and
raising ``OverflowError: cannot convert float infinity to integer``. Observed
live on **both** frequency fits used by the diagnostics:
``decaying_sinusoid`` (RID 75720/75721, Rabi up) and ``detuned_square_pulse``
(RID 75722, down-vs-up line centre); each crashed its analyze stage and persisted
nothing. The Gaussian line-centre fit has no such initialiser and survives
(RID 75718).

An unguarded fit in the ``CustomAnalysis`` would propagate that exception out of
``analyze()`` and drop *every* persisted output for the run (including any sibling
analyses). The guard must instead log and push NaN for the failed fit's channels
and let the rest of the analyze stage proceed.
"""

import numpy as np
import pytest

from repository.diagnostics.dataset_fit_analysis import FitOutput
from repository.diagnostics.dataset_fit_analysis import make_dataset_fit_analysis


# Repeated x-values reproduce the num_repeats=2 failure: zero min sample spacing
# -> the frequency-estimating initialisers do int(.../min_step) with f_max=inf.
_X = np.array([5e-6, 5e-6, 12e-6, 12e-6, 20e-6, 20e-6, 55e-6, 55e-6])
_Y = np.array([0.98, 0.99, 0.95, 0.97, 0.90, 0.92, 0.20, 0.21])

# Both frequency-estimating fits the diagnostics use crash on the repeat-x data;
# (fit_type, fit_constants, representative result key) for each.
_CRASHING_FITS = [
    ("decaying_sinusoid", {"t_dead": 0}, "t_max_transfer"),
    ("detuned_square_pulse", None, "offset"),
]

# Sentinels used as the param-handle / result-channel keys into the analyse dicts.
_X_KEY = object()
_Y_KEY = object()


class _CapturingChannel:
    """Stands in for an ndscan FloatChannel: records pushed values."""

    def __init__(self):
        self.pushed = []

    def push(self, value):
        self.pushed.append(value)


def _run_analyse(analysis_list, channels):
    """Invoke the CustomAnalysis' analyse function as ndscan's analyze() would."""
    (custom_analysis,) = analysis_list
    analyse_fn = custom_analysis._analyze_fn
    return analyse_fn({_X_KEY: _X}, {_Y_KEY: _Y}, channels)


@pytest.mark.parametrize("fit_type, fit_constants, key", _CRASHING_FITS)
def test_raw_fit_raises_on_this_data(fit_type, fit_constants, key):
    """Precondition: the raw oitg fit really does raise on the repeat-x data,
    so the guard below exercises the real failure, not a strawman. Covers both
    frequency fits that crashed live (decaying_sinusoid 75720, detuned_square_pulse
    75722)."""
    import oitg.fitting

    fit_obj = getattr(oitg.fitting, fit_type)
    kwargs = {"constants": fit_constants} if fit_constants else {}
    with pytest.raises(Exception):
        fit_obj.fit(_X, _Y, **kwargs)


@pytest.mark.parametrize("fit_type, fit_constants, key", _CRASHING_FITS)
def test_fit_failure_pushes_nan_not_raise(fit_type, fit_constants, key):
    """The guarded analysis pushes NaN (value and error) instead of crashing -
    for every fit_type whose initialiser blows up on repeat-x data."""
    analysis = make_dataset_fit_analysis(
        fit_type=fit_type,
        x=_X_KEY,
        y=_Y_KEY,
        fit_constants=fit_constants,
        outputs=[FitOutput("val", "v", fit_key=key)],
    )
    channels = {"val": _CapturingChannel(), "val_err": _CapturingChannel()}

    # Must not raise.
    _run_analyse(analysis, channels)

    assert len(channels["val"].pushed) == 1
    assert np.isnan(channels["val"].pushed[0])
    assert np.isnan(channels["val_err"].pushed[0])


def test_sibling_outputs_all_get_nan_on_failure():
    """A failed fit pushes NaN for *every* output of that analysis, so the
    analyze stage stays consistent (no half-populated channels)."""
    analysis = make_dataset_fit_analysis(
        fit_type="decaying_sinusoid",
        x=_X_KEY,
        y=_Y_KEY,
        fit_constants={"t_dead": 0},
        outputs=[
            FitOutput("pi_time", "pi", fit_key="t_max_transfer", unit="us"),
            FitOutput("rabi_frequency", "rabi", fit_key="omega", unit="kHz"),
        ],
    )
    channels = {
        name: _CapturingChannel()
        for name in ("pi_time", "pi_time_err", "rabi_frequency", "rabi_frequency_err")
    }

    _run_analyse(analysis, channels)

    for name, chan in channels.items():
        assert len(chan.pushed) == 1, name
        assert np.isnan(chan.pushed[0]), name


def test_wrong_fit_key_still_raises():
    """A misconfigured FitOutput (fit_key absent from a *successful* fit's results)
    is a programming bug, not bad data - it must stay a hard failure, not be
    swallowed into a silent NaN. Uses clean Gaussian data so the fit succeeds and
    the only failure is the bogus key in out.extract."""
    x = np.linspace(-3e3, 3e3, 41)
    y = 0.1 + 0.8 * np.exp(-((x - 200.0) ** 2) / (2 * 500.0**2))

    analysis = make_dataset_fit_analysis(
        fit_type="gaussian",
        x=_X_KEY,
        y=_Y_KEY,
        outputs=[FitOutput("bogus", "bogus", fit_key="not_a_real_key", unit="Hz")],
    )
    (custom_analysis,) = analysis
    channels = {"bogus": _CapturingChannel(), "bogus_err": _CapturingChannel()}

    with pytest.raises(KeyError):
        custom_analysis._analyze_fn({_X_KEY: x}, {_Y_KEY: y}, channels)


def test_successful_fit_still_pushes_real_values():
    """The guard does not mask a healthy fit: clean data yields real numbers."""
    # A well-conditioned Gaussian line (no duplicate x), distinct from the failing
    # decaying_sinusoid case, so the happy path is covered without the repeat-x
    # pathology.
    x = np.linspace(-3e3, 3e3, 41)
    y = 0.1 + 0.8 * np.exp(-((x - 200.0) ** 2) / (2 * 500.0**2))

    analysis = make_dataset_fit_analysis(
        fit_type="gaussian",
        x=_X_KEY,
        y=_Y_KEY,
        outputs=[FitOutput("line_centre", "centre", fit_key="x0", unit="Hz")],
    )
    (custom_analysis,) = analysis
    channels = {"line_centre": _CapturingChannel(), "line_centre_err": _CapturingChannel()}
    custom_analysis._analyze_fn({_X_KEY: x}, {_Y_KEY: y}, channels)

    (centre,) = channels["line_centre"].pushed
    assert not np.isnan(centre)
    assert abs(centre - 200.0) < 100.0


# --- Inverted clock-Rabi flop fit (the diag_clock_rabi pipeline) ------------
#
# The clock readout is inverted: excitation_fraction is the surviving ground
# population, so the flop starts HIGH (~1) and DIPS at the pi pulse. The flop
# also starts after a real ~10 us dead-time (OPLL ramp still settling). The
# diag_clock_rabi analysis fits 1 - excitation with t_dead free, averaging the
# num_repeats duplicates and dropping unphysical survival > 1 outliers. These
# tests gate that LOGIC on a *synthetic* clean flop with a known pi-time, rather
# than on contrast-starved real data (whose physics, not the fit, is the limiter).

_TRUE_TPI = 55e-6
_TRUE_TDEAD = 10e-6


def _synthetic_inverted_flop(pulse_times, tpi=_TRUE_TPI, t_dead=_TRUE_TDEAD):
    """Survival (excitation_fraction) of a clean inverted Rabi flop with dead-time.

    survival = 1 for t <= t_dead (flop has not started), then
    survival = cos^2(pi*(t - t_dead)/(2*tpi)) so it dips to its minimum at the
    pi pulse t = t_dead + tpi. (Inverting -> 1 - survival -> a normal rise-from-
    zero flop whose first maximum / t_max_transfer is at t_dead + tpi.)
    """
    t = np.asarray(pulse_times, dtype=float)
    driven = np.clip(t - t_dead, 0.0, None)
    survival = np.cos(np.pi * driven / (2 * tpi)) ** 2
    return np.where(t <= t_dead, 1.0, survival)


def _rabi_analysis():
    """The exact diag_clock_rabi persisted-analysis config."""
    return make_dataset_fit_analysis(
        fit_type="decaying_sinusoid",
        x=_X_KEY,
        y=_Y_KEY,
        y_transform=lambda ys: 1.0 - ys,
        y_valid_range=(0.0, 1.05),
        average_repeats=True,
        outputs=[
            FitOutput("pi_time", "pi", fit_key="t_max_transfer", unit="us"),
            FitOutput(
                "rabi_frequency",
                "rabi",
                derive=lambda r, e: (
                    1.0 / (2.0 * r["t_max_transfer"]),
                    e.get("t_max_transfer", float("nan"))
                    / (2.0 * r["t_max_transfer"] ** 2),
                ),
                unit="kHz",
            ),
        ],
    )


def test_inverted_rabi_recovers_pi_from_the_dip():
    """On a clean inverted flop with a real dead-time, the persisted pi_time
    lands on the dip (t_dead + tpi), not the spurious early rise-from-zero
    maximum a t_dead=0 fit of the un-inverted data would report."""
    # num_repeats=2 duplicates + a couple of unphysical survival>1 outliers, just
    # like the real readout, to exercise average_repeats + y_valid_range together.
    base = np.linspace(5e-6, 200e-6, 40)
    x = np.repeat(base, 2)
    y = _synthetic_inverted_flop(x)
    rng = np.random.default_rng(0)
    y = y + rng.normal(0, 0.01, size=y.shape)
    y[3] = 1.32  # unphysical survival-norm outliers that must be dropped
    y[17] = 1.18

    channels = {
        name: _CapturingChannel()
        for name in ("pi_time", "pi_time_err", "rabi_frequency", "rabi_frequency_err")
    }
    (custom_analysis,) = _rabi_analysis()
    custom_analysis._analyze_fn({_X_KEY: x}, {_Y_KEY: y}, channels)

    (pi_time,) = channels["pi_time"].pushed
    expected_dip = _TRUE_TDEAD + _TRUE_TPI  # 65 us
    assert not np.isnan(pi_time)
    assert abs(pi_time - expected_dip) < 8e-6, f"pi_time={pi_time * 1e6:.1f} us"

    (rabi,) = channels["rabi_frequency"].pushed
    assert abs(rabi - 1.0 / (2.0 * expected_dip)) < 2e3


def test_average_repeats_avoids_the_duplicate_x_crash():
    """With average_repeats=True the duplicate-x decaying_sinusoid fit succeeds
    (real pi_time), where the un-averaged fit would hit the int(inf) crash and
    push NaN."""
    base = np.linspace(5e-6, 200e-6, 40)
    x = np.repeat(base, 2)
    y = _synthetic_inverted_flop(x)

    channels = {
        name: _CapturingChannel()
        for name in ("pi_time", "pi_time_err", "rabi_frequency", "rabi_frequency_err")
    }
    (custom_analysis,) = _rabi_analysis()
    custom_analysis._analyze_fn({_X_KEY: x}, {_Y_KEY: y}, channels)

    (pi_time,) = channels["pi_time"].pushed
    assert not np.isnan(pi_time)


def test_y_valid_range_drops_unphysical_points():
    """y_valid_range removes survival>1 outliers before the fit; a fit dominated
    by them (kept) would land somewhere very different."""
    x = np.linspace(-100e3, 100e3, 41)
    # a clean inverted-Lorentzian-ish dip line plus a couple of >1 spikes
    y = 0.85 - 0.2 / (1 + ((x - (-37e3)) / 17e3) ** 2)
    y[5] = 1.4
    y[30] = 1.3

    analysis = make_dataset_fit_analysis(
        fit_type="lorentzian",
        x=_X_KEY,
        y=_Y_KEY,
        y_valid_range=(0.0, 1.05),
        outputs=[FitOutput("centre", "c", fit_key="x0", unit="Hz")],
    )
    (custom_analysis,) = analysis
    channels = {"centre": _CapturingChannel(), "centre_err": _CapturingChannel()}
    custom_analysis._analyze_fn({_X_KEY: x}, {_Y_KEY: y}, channels)

    (centre,) = channels["centre"].pushed
    assert not np.isnan(centre)
    assert abs(centre - (-37e3)) < 15e3
