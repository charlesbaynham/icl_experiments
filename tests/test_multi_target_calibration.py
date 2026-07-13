"""Multi-target calibration clients (WP-D): a client that maintains several
calibration leaves at once walks the *union* of their DAGs, so a dependency
shared by several targets is fixed exactly once, ahead of every node that
depends on it, and every leaf is fixed.

This mirrors the real :class:`EnsureClockPiTimes` shape (up-pi and down-pi
sharing the clock-delivery chain) with a synthetic diamond DAG::

        Root            (shared, optimum 2.0)
          ^
        SharedMid       (shared, optimum 6.0)
         ^   ^
    LeafUp   LeafDown   (the two targets; optima 4.0 / 7.0)

Every node is a pure-host parabola "measurement" broken at its default, so the
whole walk runs on the host (no precompile pool / kernel emulator needed): the
grid optimizer's 11-point [0, 10] sweep hits each integer optimum exactly.
"""

import gc

import pytest
from ndscan.experiment.parameters import FloatParamHandle

from qbutler import CalibratedExpFragment
from qbutler import dag
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationError
from qbutler.calibration import CalibrationResult
from qbutler.calibration import check_targets
from qbutler.calibration import fix_targets

#: A synthetic check is OK only above this; the optimum scores 10.0 and the
#: nearest grid neighbour 9.0, so only the exact optimum passes.
OK_SCORE = 9.5

OPTIMA = {}


def _parabola(node, param_name, optimum):
    p = getattr(node, param_name).get()
    data = 10.0 - abs(p - optimum)
    result = CalibrationResult.OK if data > OK_SCORE else CalibrationResult.BAD_DATA
    return result, data


class Root(Calibration):
    def build_calibration(self):
        self.set_timeout(300.0)
        self.setattr_param_optimizable(
            "root_param", "Root param", min=0.0, max=10.0, default=5.0
        )
        self.root_param: FloatParamHandle

    def check_own_state(self):
        return _parabola(self, "root_param", 2.0)


class SharedMid(Calibration):
    def build_calibration(self):
        self.set_timeout(300.0)
        self.add_dependency(Root)
        self.setattr_param_optimizable(
            "mid_param", "Mid param", min=0.0, max=10.0, default=3.0
        )
        self.mid_param: FloatParamHandle

    def check_own_state(self):
        return _parabola(self, "mid_param", 6.0)


class LeafUp(Calibration):
    def build_calibration(self):
        self.set_timeout(300.0)
        self.add_dependency(SharedMid)
        self.setattr_param_optimizable(
            "up_param", "Up param", min=0.0, max=10.0, default=8.0
        )
        self.up_param: FloatParamHandle

    def check_own_state(self):
        return _parabola(self, "up_param", 4.0)


class LeafDown(Calibration):
    def build_calibration(self):
        self.set_timeout(300.0)
        self.add_dependency(SharedMid)
        self.setattr_param_optimizable(
            "down_param", "Down param", min=0.0, max=10.0, default=1.0
        )
        self.down_param: FloatParamHandle

    def check_own_state(self):
        return _parabola(self, "down_param", 7.0)


class _MultiTargetClientFrag(CalibratedExpFragment):
    """Two leaves, both maintained — the shape EnsureClockPiTimes now uses."""

    def build_fragment(self):
        self.setattr_calibration(LeafUp)
        self.LeafUp: LeafUp
        self.setattr_calibration(LeafDown)
        self.LeafDown: LeafDown
        self.calibration_targets = [self.LeafUp, self.LeafDown]

    def run_once(self):  # host no-op: these tests exercise the walk, not a scan
        pass


class _SingleAttachedClientFrag(CalibratedExpFragment):
    """One calibration attached, nothing declared: auto-discovery still works."""

    def build_fragment(self):
        self.setattr_calibration(LeafUp)
        self.LeafUp: LeafUp

    def run_once(self):
        pass


class _AmbiguousClientFrag(CalibratedExpFragment):
    """Two attached, neither target declared: must fail loudly."""

    def build_fragment(self):
        self.setattr_calibration(LeafUp)
        self.LeafUp: LeafUp
        self.setattr_calibration(LeafDown)
        self.LeafDown: LeafDown

    def run_once(self):
        pass


@pytest.fixture(autouse=True)
def _clear_dag():
    gc.collect()
    dag._dependency_map.clear()
    yield
    dag._dependency_map.clear()


def _arm(nodes):
    for node in nodes:
        node.host_setup()


def _instrument_fix_counts(nodes):
    counts = {}
    order = []
    for node in nodes:
        original = node._do_fix_own_state

        def _wrapped(_node=node, _orig=original):
            name = type(_node).__name__
            counts[name] = counts.get(name, 0) + 1
            order.append(name)
            return _orig()

        node._do_fix_own_state = _wrapped
    return counts, order


def _committed(node, attr):
    return getattr(node, attr).get()


# --------------------------------------------------------------------------- #
# Union-order DAG helper
# --------------------------------------------------------------------------- #


def test_union_dependencies_orders_shared_dep_first(fragment_factory):
    frag = fragment_factory(_MultiTargetClientFrag)
    targets = frag._resolve_targets()
    union = dag.get_union_dependencies(targets)
    names = [type(n).__name__ for n in union]

    assert set(names) == {"Root", "SharedMid", "LeafUp", "LeafDown"}
    assert len(names) == 4, "each node appears exactly once in the union"
    # Every dependency precedes the node that depends on it.
    assert names.index("Root") < names.index("SharedMid")
    assert names.index("SharedMid") < names.index("LeafUp")
    assert names.index("SharedMid") < names.index("LeafDown")


# --------------------------------------------------------------------------- #
# fix_targets: shared dependency fixed once, both leaves fixed
# --------------------------------------------------------------------------- #


def test_fix_targets_fixes_shared_dep_once_and_both_leaves(fragment_factory):
    frag = fragment_factory(_MultiTargetClientFrag)
    targets = frag._resolve_targets()
    union = dag.get_union_dependencies(targets)
    _arm(union)
    counts, order = _instrument_fix_counts(union)

    assert check_targets(targets, force=True)[0] != CalibrationResult.OK
    fix_targets(targets)
    assert check_targets(targets, force=True)[0] == CalibrationResult.OK

    # The load-bearing WP-D assertion: fix-call counts, not just final state.
    assert counts == {"Root": 1, "SharedMid": 1, "LeafUp": 1, "LeafDown": 1}
    # Shared nodes are fixed before either leaf.
    assert order.index("Root") < order.index("SharedMid")
    assert order.index("SharedMid") < order.index("LeafUp")
    assert order.index("SharedMid") < order.index("LeafDown")

    by_type = {type(n): n for n in union}
    assert _committed(by_type[Root], "root_param") == pytest.approx(2.0)
    assert _committed(by_type[SharedMid], "mid_param") == pytest.approx(6.0)
    assert _committed(by_type[LeafUp], "up_param") == pytest.approx(4.0)
    assert _committed(by_type[LeafDown], "down_param") == pytest.approx(7.0)


def test_fix_targets_empty_is_noop():
    # Must not raise or walk anything.
    fix_targets([])
    assert check_targets([]) == (CalibrationResult.OK, None)


# --------------------------------------------------------------------------- #
# Client wiring: resolve, needs-recalibration, recalibrate
# --------------------------------------------------------------------------- #


def test_client_resolves_declared_targets(fragment_factory):
    frag = fragment_factory(_MultiTargetClientFrag)
    targets = frag._resolve_targets()
    assert [type(t).__name__ for t in targets] == ["LeafUp", "LeafDown"]


def test_client_auto_discovers_single_target(fragment_factory):
    frag = fragment_factory(_SingleAttachedClientFrag)
    targets = frag._resolve_targets()
    assert [type(t).__name__ for t in targets] == ["LeafUp"]


def test_client_ambiguous_targets_raise(fragment_factory):
    frag = fragment_factory(_AmbiguousClientFrag)
    with pytest.raises(CalibrationError):
        frag._resolve_targets()


def test_needs_recalibration_then_recalibrate(fragment_factory):
    frag = fragment_factory(_MultiTargetClientFrag)
    union = dag.get_union_dependencies(frag._resolve_targets())
    _arm(union)

    assert frag._needs_recalibration() is True
    frag._recalibrate()
    assert frag._needs_recalibration() is False
