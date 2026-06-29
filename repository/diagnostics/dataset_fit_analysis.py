r"""
Dataset-outputting fit analyses for the atom diagnostics.

The diagnostics originally fitted their scans with :class:`ndscan.experiment.OnlineFit`
only. ``OnlineFit`` runs *online* and draws the fit on the live plot, but it does
**not** write the fitted parameters anywhere: nothing about the diagnosed quantity
(line centre, Rabi frequency, polarization axis, ...) lands in the experiment's
result datasets. That makes the diagnostics good for eyeballing but useless for
logging / trending / downstream analysis.

ndscan provides a second analysis type for exactly this -
:class:`ndscan.experiment.CustomAnalysis` - which runs a user fit function once at
the end of the scan and ``push``-es its outputs into real
:class:`ndscan.experiment.FloatChannel` result channels (see
``vendor/ndscan/examples/rabi_flop_fit.py`` and
``repository/tests/ndscan_tests/rabi_flow_analysis.py``). Those channels are stored
in the dataset like any per-shot result.

This module wraps that pattern so each diagnostic can keep its live ``OnlineFit``
*and* additionally emit the fitted value(s) to the dataset with a couple of lines.
The offline fit is performed with :mod:`oitg.fitting` - the same fit library ndscan
drives for ``OnlineFit`` - so the online and dataset fits agree.

Usage::

    def get_default_analyses(self):
        return super().get_default_analyses() + make_dataset_fit_analysis(
            fit_type="lorentzian",
            x=self.extra_clock_detuning,
            y=self.excitation_fraction,
            outputs=[
                FitOutput("line_centre", "Fitted line centre", "x0", unit="kHz"),
            ],
        )

``make_dataset_fit_analysis`` returns a ``[CustomAnalysis(...)]`` list so it can be
concatenated straight onto the existing ``OnlineFit`` list.
"""

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
from ndscan.experiment import CustomAnalysis
from ndscan.experiment import FloatChannel

logger = logging.getLogger(__name__)


@dataclass
class FitOutput:
    """One fitted quantity to push into a dataset result channel.

    Two result channels are created per output: ``<name>`` (the value) and
    ``<name>_err`` (its fit uncertainty).

    :param name: Result-channel name for the fitted value.
    :param description: Human-readable description (Sphinx / dashboard).
    :param fit_key: Key into the :mod:`oitg.fitting` result/error dicts to read the
        value and its error from (e.g. ``"x0"`` for a Lorentzian centre). Mutually
        exclusive with ``derive``.
    :param unit: Display unit for the channel (base-SI value stored, as always).
    :param derive: Optional ``f(fit_results, fit_errs) -> (value, error)`` to compute
        a *derived* quantity (e.g. a Rabi frequency from a fitted pi-time) instead of
        reading a raw fit key. Mutually exclusive with ``fit_key``.
    """

    name: str
    description: str
    fit_key: str | None = None
    unit: str = ""
    derive: Callable[[dict, dict], tuple[float, float]] | None = None

    def extract(self, fit_results: dict, fit_errs: dict) -> tuple[float, float]:
        if self.derive is not None:
            return self.derive(fit_results, fit_errs)
        if self.fit_key is None:
            raise ValueError(
                f"FitOutput '{self.name}' needs either fit_key or derive set"
            )
        return fit_results[self.fit_key], fit_errs.get(self.fit_key, float("nan"))


def make_dataset_fit_analysis(
    fit_type: str,
    x,
    y,
    outputs: list[FitOutput],
    fit_constants: dict | None = None,
    fit_initial_values: dict | None = None,
    y_transform: Callable[[np.ndarray], np.ndarray] | None = None,
    y_valid_range: tuple[float, float] | None = None,
    average_repeats: bool = False,
):
    r"""Build a :class:`CustomAnalysis` that fits ``y`` vs ``x`` into a dataset.

    Pairs with a live ``OnlineFit`` of the same ``fit_type``: the ``OnlineFit`` draws
    the live curve, this writes the fitted numbers into result channels so they are
    stored in the dataset.

    :param fit_type: An :mod:`oitg.fitting` procedure name, e.g. ``"lorentzian"``,
        ``"decaying_sinusoid"``, ``"sinusoid"`` - the same names ``OnlineFit`` uses.
    :param x: Scan-axis parameter handle supplying the x data.
    :param y: Result channel supplying the y data.
    :param outputs: Quantities to push to the dataset (see :class:`FitOutput`).
    :param fit_constants: Parameters held constant during the fit (e.g.
        ``{"t_dead": 0}``), forwarded to ``oitg.fitting``.
    :param fit_initial_values: Initial fit-parameter guesses, forwarded to
        ``oitg.fitting``.
    :param y_transform: Optional ``f(ys) -> ys`` applied to the y data before
        fitting. Used by the clock-Rabi diagnostics to fit ``1 - excitation`` so an
        *inverted* readout (survival, which dips at the pi pulse) is fitted as a
        normal rise-from-zero flop and ``t_max_transfer`` lands on the pi-pulse. The
        paired ``OnlineFit`` must apply the *same* transform (e.g. via a transformed
        result channel) so the online and persisted fits agree.
    :param y_valid_range: Optional ``(lo, hi)``; points whose *original* y falls
        outside it are dropped before fitting. The normalised-survival readout
        occasionally emits unphysical values (>1) when the atom-number reference is
        noisy; dropping them stops a few outliers from dominating the fit. Applied
        to the y data as read, before ``y_transform``.
    :param average_repeats: If ``True``, average the y values sharing each x before
        fitting. ``num_repeats > 1`` scans repeat every x value, which leaves
        duplicate x points; ``decaying_sinusoid``'s initialiser takes ``0.5 /
        min(diff(x))`` and a zero minimum spacing makes that ``inf`` -> ``int(inf)``
        raises (the RID 75720 crash). Averaging repeats removes the duplicates (and
        denoises) so the fit is well-posed; the crash-guard still covers any other
        failure.
    :return: ``[CustomAnalysis(...)]`` - a one-element list, ready to concatenate onto
        the diagnostic's ``OnlineFit`` list.
    """

    result_channels = []
    for out in outputs:
        result_channels.append(FloatChannel(out.name, out.description, unit=out.unit))
        result_channels.append(
            FloatChannel(
                out.name + "_err", out.description + " (fit error)", unit=out.unit
            )
        )

    def _analyse(axis_values, result_values, analysis_results):
        # oitg.fitting is only importable inside the ARTIQ/Nix runtime; import lazily
        # so this module stays importable (and unit-test-collectable) without it.
        import oitg.fitting

        fit_obj = getattr(oitg.fitting, fit_type)

        xs = np.array(axis_values[x], dtype=float)
        ys = np.array(result_values[y], dtype=float)

        if y_valid_range is not None:
            lo, hi = y_valid_range
            keep = (ys >= lo) & (ys <= hi)
            xs = xs[keep]
            ys = ys[keep]

        if y_transform is not None:
            ys = y_transform(ys)

        if average_repeats and xs.size:
            ux = np.unique(xs)
            if ux.size != xs.size:
                ys = np.array([ys[xs == u].mean() for u in ux])
                xs = ux

        kwargs = {}
        if fit_constants:
            kwargs["constants"] = fit_constants
        if fit_initial_values:
            kwargs["initialise"] = fit_initial_values

        # A diagnostic fit can fail on real data - a degenerate scan (e.g. the
        # num_repeats=2 duplicate x-values make decaying_sinusoid's initialiser
        # divide by zero -> int(inf), RID 75720) makes oitg raise rather than
        # return. That must not take down the whole scan's analyze stage (which
        # would drop *every* persisted output, including sibling analyses); push
        # NaN for this fit's channels and carry on. The live OnlineFit still draws
        # what it can.
        #
        # Only the fit itself is guarded. A misconfigured FitOutput (wrong
        # fit_key, missing derive/fit_key) is a programming bug in the diagnostic,
        # not bad data: let out.extract raise so it stays a hard, fix-it failure
        # rather than degrading to a silent NaN on every run.
        try:
            fit_results, fit_errs = fit_obj.fit(xs, ys, **kwargs)
        except Exception:
            logger.warning(
                "dataset fit '%s' failed; pushing NaN for %s",
                fit_type,
                [out.name for out in outputs],
                exc_info=True,
            )
            extracted = [(float("nan"), float("nan")) for _ in outputs]
        else:
            extracted = [out.extract(fit_results, fit_errs) for out in outputs]

        for out, (value, error) in zip(outputs, extracted):
            analysis_results[out.name].push(value)
            analysis_results[out.name + "_err"].push(error)

        # No annotations: the paired OnlineFit already draws the live curve. This
        # analysis exists purely to emit the fitted numbers to the dataset.
        return []

    return [CustomAnalysis([x], _analyse, result_channels)]
