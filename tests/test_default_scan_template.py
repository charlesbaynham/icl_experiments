"""Host-side checks for the ``default_scan`` template (PR #37).

The template (``repository/lib/experiment_templates/default_scan.py``) seeds a
default ndscan scan so a diagnostic submitted with ``arguments={}`` already runs
a real scan. Its ``_DefaultScanArgumentInterface.build`` re-implements
``ndscan.experiment.entry_point.ArgumentInterface.build`` (to inject the seeded
``scan`` section); that coupling is the reason the template needed checking on
the rig before merge.

The seeded-default behaviour is already confirmed live (a diagnostic ran its
seeded scan on the rig). What a default-only science run does *not* exercise -
and what these host-side tests cover - is the rest of job-card step 1:

* a dashboard **override** of the scan wins over the seeded default, and
* an **emptied** scan falls back to ``no_axes_mode`` cleanly.

Both are argument-build behaviours (``make_scan_spec`` reads ``ndscan_params``),
so they are fully testable host-side with the mocked managers - no core device,
no atoms. We assert against ``ArgumentInterface.make_scan_spec`` (what
``FragmentScanExperiment.prepare`` consumes) rather than poke private state.
"""

import copy

from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.utils import PARAMS_ARG_KEY

from repository.diagnostics.diag_clock_rabi import ClockRabiUpBeamDiagnostic
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp

_AXIS_PARAM = "spectroscopy_pulse_time"
_SEEDED_START = 5e-6
_SEEDED_STOP = 300e-6
_SEEDED_NUM_POINTS = 40
_SEEDED_NUM_REPEATS = 2


class _ToyFrag(ExpFragment):
    """Minimal fragment with one free param, to test the template in isolation
    from any real diagnostic's (physics-tunable) scan constants."""

    def build_fragment(self):
        self.setattr_param("foo", FloatParam, "foo", default=0.0)
        self.foo: FloatParamHandle

    def run_once(self):
        pass


_TOY_START, _TOY_STOP, _TOY_POINTS, _TOY_REPEATS = 0.0, 1.0, 3, 4
ToyDefaultScan = make_default_scan_exp(
    _ToyFrag,
    default_axes=[
        DefaultScanAxis(param="foo", start=_TOY_START, stop=_TOY_STOP, num_points=_TOY_POINTS),
    ],
    default_num_repeats=_TOY_REPEATS,
)


def _build_with_params(device_mgr, dataset_mgr, exp_class=ClockRabiUpBeamDiagnostic,
                       ndscan_params=None):
    """Build a default-scan experiment, optionally overriding ndscan_params.

    Mirrors how the master builds a submitted experiment: a fresh
    ``ProcessArgumentManager`` carrying the arguments. The ``ndscan_params``
    argument is a ``PYONValue``, so (as the master does) it is supplied as a
    PYON-encoded string, not a raw dict.
    """
    from artiq.language.environment import ProcessArgumentManager
    from sipyco import pyon

    arguments = {}
    if ndscan_params is not None:
        arguments[PARAMS_ARG_KEY] = pyon.encode(ndscan_params)

    argument_mgr = ProcessArgumentManager(arguments)
    return exp_class((device_mgr, dataset_mgr, argument_mgr, None))


def _single_axis(spec):
    assert len(spec.axes) == 1, f"expected one scan axis, got {len(spec.axes)}"
    axis = spec.axes[0]
    generator = spec.generators[0]
    fqn = axis.param_schema["fqn"]
    return axis, generator, fqn


def test_template_seeds_declared_scan(device_mgr, dataset_mgr):
    """The template's value-add: arguments={} seeds the declared DefaultScanAxis
    (FQN resolved by param name, range/points/repeats) instead of an empty scan.

    Uses a throwaway fragment so this stays decoupled from any real diagnostic's
    (physics-tunable) scan constants - a retune of a diagnostic must not redden
    this template test.
    """
    exp = _build_with_params(device_mgr, dataset_mgr, exp_class=ToyDefaultScan)

    spec, _, _ = exp.args.make_scan_spec()
    _, generator, fqn = _single_axis(spec)

    assert fqn.rsplit(".", 1)[-1] == "foo"
    points = generator.points_for_level(0)
    assert len(points) == _TOY_POINTS
    assert min(points) == _TOY_START
    assert max(points) == _TOY_STOP
    assert spec.options.num_repeats == _TOY_REPEATS


def test_seeded_default_scan_on_real_diagnostic(device_mgr, dataset_mgr):
    """End-to-end through a real diagnostic's fragment stack: arguments={} runs the
    seeded scan, not a single default point. (Constants mirror the live RID 75718-
    era ClockRabiUpBeamDiagnostic default; a deliberate retune would update these.)
    """
    exp = _build_with_params(device_mgr, dataset_mgr)

    spec, _, _ = exp.args.make_scan_spec()
    _, generator, fqn = _single_axis(spec)

    assert fqn.rsplit(".", 1)[-1] == _AXIS_PARAM
    points = generator.points_for_level(0)
    assert len(points) == _SEEDED_NUM_POINTS
    assert min(points) == _SEEDED_START
    assert max(points) == _SEEDED_STOP
    assert spec.options.num_repeats == _SEEDED_NUM_REPEATS


def test_dashboard_override_wins(device_mgr, dataset_mgr):
    """A supplied ndscan_params with a different range/points overrides the seed."""
    # Take the seeded desc the template produced, then mutate the scan section as
    # the dashboard would when the user edits the axis range/points/repeats.
    seeded = _build_with_params(device_mgr, dataset_mgr)
    desc = copy.deepcopy(seeded.args._params)

    new_start, new_stop, new_points, new_repeats = 10e-6, 120e-6, 7, 5
    assert len(desc["scan"]["axes"]) == 1
    desc["scan"]["axes"][0]["range"] = {
        "start": new_start,
        "stop": new_stop,
        "num_points": new_points,
        "randomise_order": False,
    }
    desc["scan"]["num_repeats"] = new_repeats

    exp = _build_with_params(device_mgr, dataset_mgr, ndscan_params=desc)
    spec, _, _ = exp.args.make_scan_spec()
    _, generator, fqn = _single_axis(spec)

    assert fqn.rsplit(".", 1)[-1] == _AXIS_PARAM
    points = generator.points_for_level(0)
    assert len(points) == new_points
    assert min(points) == new_start
    assert max(points) == new_stop
    assert spec.options.num_repeats == new_repeats


def test_emptied_scan_falls_back_to_no_axes_mode(device_mgr, dataset_mgr):
    """Emptying the axes leaves no scan axis and honours no_axes_mode cleanly."""
    from ndscan.utils import NoAxesMode

    seeded = _build_with_params(device_mgr, dataset_mgr)
    desc = copy.deepcopy(seeded.args._params)
    desc["scan"]["axes"] = []
    desc["scan"]["no_axes_mode"] = "single"

    exp = _build_with_params(device_mgr, dataset_mgr, ndscan_params=desc)
    spec, no_axes_mode, _ = exp.args.make_scan_spec()

    assert spec.axes == []
    assert no_axes_mode == NoAxesMode.single
