"""Host-side checks for ``make_dataset_fit_analysis`` (PR #37).

A diagnostic's dataset-output fit can fail on real data. Concretely, every
diagnostic seeds ``default_num_repeats = 2``, so each scan x-value appears twice;
``oitg.fitting.decaying_sinusoid``'s initialiser then computes
``int(f_max / f_min)`` with ``f_max = 0.5 / min_step`` and a zero ``min_step``
(duplicate adjacent samples), raising ``OverflowError: cannot convert float
infinity to integer`` (observed live, RID 75720 - the Rabi-up diagnostic, whose
analyze stage crashed and persisted no ``pi_time``).

An unguarded fit in the ``CustomAnalysis`` would propagate that exception out of
``analyze()`` and drop *every* persisted output for the run (including any sibling
analyses). The guard must instead log and push NaN for the failed fit's channels
and let the rest of the analyze stage proceed.
"""

import numpy as np
import pytest

from repository.diagnostics.dataset_fit_analysis import FitOutput
from repository.diagnostics.dataset_fit_analysis import make_dataset_fit_analysis


# Repeated x-values reproduce RID 75720: num_repeats=2 -> zero min sample spacing
# -> decaying_sinusoid initialiser does int(f_max/f_min) with f_max=inf.
_X = np.array([5e-6, 5e-6, 12e-6, 12e-6, 20e-6, 20e-6, 55e-6, 55e-6])
_Y = np.array([0.98, 0.99, 0.95, 0.97, 0.90, 0.92, 0.20, 0.21])

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


def test_raw_decaying_sinusoid_fit_raises_on_this_data():
    """Precondition: the raw oitg fit really does raise on the RID 75720 data,
    so the guard below is exercising the real failure, not a strawman."""
    import oitg.fitting

    with pytest.raises(Exception):
        oitg.fitting.decaying_sinusoid.fit(_X, _Y, constants={"t_dead": 0})


def test_fit_failure_pushes_nan_not_raise():
    """The guarded analysis pushes NaN (value and error) instead of crashing."""
    analysis = make_dataset_fit_analysis(
        fit_type="decaying_sinusoid",
        x=_X_KEY,
        y=_Y_KEY,
        fit_constants={"t_dead": 0},
        outputs=[
            FitOutput("pi_time", "pi", fit_key="t_max_transfer", unit="us"),
        ],
    )
    channels = {"pi_time": _CapturingChannel(), "pi_time_err": _CapturingChannel()}

    # Must not raise.
    _run_analyse(analysis, channels)

    assert len(channels["pi_time"].pushed) == 1
    assert np.isnan(channels["pi_time"].pushed[0])
    assert np.isnan(channels["pi_time_err"].pushed[0])


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
