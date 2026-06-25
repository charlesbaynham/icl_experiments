r"""
Helper for building *default-runnable* ndscan scan experiments.

A plain :func:`ndscan.experiment.entry_point.make_fragment_scan_exp` produces an
experiment whose scan-axis list defaults to **empty** - submitting it with no
arguments runs a single point at the parameter defaults. For a *diagnostic*
experiment we want the opposite: submitting with ``arguments={}`` should already
run a sensible scan and return the diagnosed quantity, with no hand-tuning at
submit time. The scan axis remains fully overridable in the dashboard / via
explicit arguments - we only change the *default*.

The scan axes in ndscan are carried entirely by the ``ndscan_params`` PYON
argument, whose default is seeded in :meth:`ArgumentInterface.build` as
``desc["scan"]["axes"] = []``. This module subclasses ``ArgumentInterface`` to
seed that list from a declarative spec instead, and subclasses
``FragmentScanExperiment`` to use it.

The scan axes are resolved to their fully-qualified parameter names (FQNs) *by
parameter name* from the schemata collected at build time, so we never hardcode
which mixin happens to declare a given parameter (robust against refactors).

Usage::

    from repository.lib.experiment_templates.default_scan import (
        DefaultScanAxis,
        make_default_scan_exp,
    )

    MyDiagnostic = make_default_scan_exp(
        MyFragment,
        default_axes=[
            DefaultScanAxis(
                param="spectroscopy_pulse_time",
                start=0.0,
                stop=120e-6,
                num_points=25,
            ),
        ],
        default_num_repeats=2,
    )
"""

import logging
from dataclasses import dataclass

from artiq.language import PYONValue
from ndscan.experiment.entry_point import ArgumentInterface
from ndscan.experiment.entry_point import FragmentScanExperiment
from ndscan.utils import PARAMS_ARG_KEY

logger = logging.getLogger(__name__)


@dataclass
class DefaultScanAxis:
    """Declarative default scan axis, resolved to an FQN by parameter name.

    :param param: The (unqualified) parameter name to scan, e.g.
        ``"spectroscopy_pulse_time"``. It must be a free parameter of the
        top-level fragment.
    :param start: Linear-scan start value (in base SI units, matching the
        parameter's stored value - e.g. seconds, amps, Hz; *not* the display
        unit).
    :param stop: Linear-scan stop value (base SI units).
    :param num_points: Number of equally spaced points.
    :param randomise_order: Randomise the per-point order within the axis.
    :param path: Fragment path of the parameter; ``""`` is the top-level
        fragment (the usual case).
    """

    param: str
    start: float
    stop: float
    num_points: int
    randomise_order: bool = False
    path: str = ""


class _DefaultScanArgumentInterface(ArgumentInterface):
    """``ArgumentInterface`` that seeds default scan axes / repeats.

    The default axes and repeat count are injected into the PYON ``desc`` *before*
    ``get_argument`` is called, so they become the argument default (still
    overridable from the dashboard).

    FIXME: This re-implements ``ArgumentInterface.build`` (copying its body to
    inject the default scan section) and so is tightly coupled to ndscan internals
    that may shift under us. It has not yet been exercised end-to-end on the live
    rig - submitting a diagnostic with ``arguments={}`` and confirming the seeded
    scan axes / repeats actually take effect in the dashboard. See
    ``.claude/plans/diagnostics_live_test_plan.md``. This FIXME deliberately blocks
    merge to master until those live checks are done; remove it once confirmed.
    """

    # Overridden per-experiment in make_default_scan_exp's subclass body.
    _default_axes: list[DefaultScanAxis] = []
    _default_num_repeats: int = 1
    _default_no_axes_mode: str = "single"

    def build(self, fragments, scannable: bool = False) -> None:
        # Mirror ArgumentInterface.build, but seed the scan section before the
        # get_argument call. We cannot call super().build() because it calls
        # get_argument itself; instead we reproduce its body and inject our axes.
        self._fragments = fragments

        instances: dict[str, list[str]] = {}
        self._schemata: dict[str, dict] = {}
        self._sample_instances = {}
        always_shown_params = []
        for fragment in fragments:
            fragment._collect_params(instances, self._schemata, self._sample_instances)

            for handle in fragment.get_always_shown_params():
                path = handle.owner._stringize_path()
                try:
                    param = handle.owner._free_params[handle.name]
                    always_shown_params += [(param.fqn, path)]
                except KeyError:
                    logger.warning(
                        "Parameter '%s' specified in get_always_shown_params()"
                        " is not a free parameter of fragment '%s'",
                        handle.name,
                        path,
                    )

        desc = {
            "instances": instances,
            "schemata": self._schemata,
            "always_shown": always_shown_params,
            "overrides": {},
        }
        if scannable:
            desc["scan"] = {
                "axes": self._build_default_axes(instances),
                "num_repeats": self._default_num_repeats,
                "no_axes_mode": self._default_no_axes_mode,
                "randomise_order_globally": False,
            }
        self._params = self.get_argument(PARAMS_ARG_KEY, PYONValue(default=desc))

    def _resolve_fqn(self, param_name: str, path: str, instances: dict) -> str:
        """Resolve an unqualified parameter name to its FQN for the given path.

        ``instances`` maps fragment path -> list of parameter FQNs. We match the
        last dotted component of the FQN to ``param_name``. Raises if not found
        or ambiguous, so a stale spec fails loudly at build time rather than
        silently running the wrong (or no) scan.
        """
        candidates = [
            fqn
            for fqn in instances.get(path, [])
            if fqn.rsplit(".", 1)[-1] == param_name
        ]
        if not candidates:
            raise ValueError(
                f"Default scan axis parameter '{param_name}' not found as a free "
                f"parameter at path '{path}'. Available: "
                f"{sorted(f.rsplit('.', 1)[-1] for f in instances.get(path, []))}"
            )
        if len(candidates) > 1:
            raise ValueError(
                f"Default scan axis parameter '{param_name}' is ambiguous at "
                f"path '{path}': {candidates}"
            )
        return candidates[0]

    def _build_default_axes(self, instances: dict) -> list[dict]:
        axes = []
        for ax in self._default_axes:
            fqn = self._resolve_fqn(ax.param, ax.path, instances)
            axes.append(
                {
                    "type": "linear",
                    "range": {
                        "start": ax.start,
                        "stop": ax.stop,
                        "num_points": ax.num_points,
                        "randomise_order": ax.randomise_order,
                    },
                    "fqn": fqn,
                    "path": ax.path,
                }
            )
        return axes


def make_default_scan_exp(
    fragment_class,
    default_axes: list[DefaultScanAxis],
    *args,
    default_num_repeats: int = 1,
    default_no_axes_mode: str = "single",
    max_rtio_underflow_retries: int = 3,
    max_transitory_error_retries: int = 10,
):
    """Like ``make_fragment_scan_exp`` but with a *default* scan baked in.

    The returned experiment, submitted with ``arguments={}``, scans the axes in
    ``default_axes`` with ``default_num_repeats`` repeats. Everything stays
    overridable from the dashboard.

    :param fragment_class: The ``ExpFragment`` subclass to scan.
    :param default_axes: List of :class:`DefaultScanAxis` describing the default
        scan (typically one axis for a 1-D diagnostic).
    :param default_num_repeats: Default number of scan repeats (averaging).
    :param default_no_axes_mode: ndscan ``NoAxesMode`` name to use if the scan is
        emptied (kept at ``"single"``; irrelevant while default axes exist).
    """

    axes = list(default_axes)
    num_repeats = default_num_repeats
    no_axes_mode = default_no_axes_mode

    class _ArgIface(_DefaultScanArgumentInterface):
        _default_axes = axes
        _default_num_repeats = num_repeats
        _default_no_axes_mode = no_axes_mode

    class DefaultScanShim(FragmentScanExperiment):
        def build(self):
            self.fragment = fragment_class(self, [], *args)
            self.max_rtio_underflow_retries = max_rtio_underflow_retries
            self.max_transitory_error_retries = max_transitory_error_retries
            self.args = _ArgIface(self, [self.fragment], scannable=True)

    DefaultScanShim.__name__ = fragment_class.__name__
    DefaultScanShim.__doc__ = fragment_class.__doc__

    return DefaultScanShim
