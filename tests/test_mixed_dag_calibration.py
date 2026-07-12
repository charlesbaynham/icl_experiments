"""The precompiled-calibration walk across a MIXED kernel/host DAG.

The kernel demo's DAG is all-kernel; this covers the case Charles asked for: a
dependency chain that alternates between kernel-checked nodes (pooled precompiled
kernels) and a HOST-ONLY node whose check/fix must fall back to running directly
on the host instead of through the :class:`~qbutler.precompile.PrecompilePool`.

Three layers of coverage:

- compile: the client's fused main kernel and the two kernel nodes' pooled
  check/optimizer kernels compile subkernel-free; the host node has no kernel and
  no ``core``; the demo is in the ``test_compile_all`` collection.
- dispatch seam: seeding pools *only* the kernel nodes; ``_do_check_own_state``
  routes the kernel nodes through the pool and the host node straight to its host
  ``check_own_state`` (the RPC-style fallback).
- full mixed walk: a real ``fix_state`` walk fixes base-first across both modes
  and the client escape/re-enter cycle completes -- driven on the host, since
  icl's test env has no kernel emulator (see module note below), with a pool that
  hands back host emulations of the on-core measurement in place of compiled
  kernels. Only the synthetic measurement is faked; the walk, the optimizer
  protocol and the host-node path are the production code.

Why host-emulated, not the real emulator: qbutler's own end-to-end walk tests are
gated behind ``--withartiq`` + ``LIBARTIQ_EMULATOR`` (its ``CoreEmulator``); icl's
test env provides neither (``device_mgr`` compiles kernels but mock-runs them, so
a real kernel check would return a ``MagicMock``, not a result). Porting the
emulator harness is out of scope, so the kernel measurement is emulated on the
host while the surrounding machinery runs for real.
"""

import gc

import pytest
from ndscan.experiment import ExpFragment
from ndscan.experiment.utils import is_kernel

from qbutler import dag
from qbutler.calibration import CalibrationEscape
from qbutler.calibration import CalibrationResult
from qbutler.client import drive_with_recalibration
from repository.calibrations.qbutler_mixed_dag_demo import OK_SCORE
from repository.calibrations.qbutler_mixed_dag_demo import MixedDagBase
from repository.calibrations.qbutler_mixed_dag_demo import MixedDagMid
from repository.calibrations.qbutler_mixed_dag_demo import MixedDagTop
from repository.calibrations.qbutler_mixed_dag_demo import QbutlerMixedDagFixDemoFrag

#: Parabola optima for the two kernel nodes, mirroring the @kernel checks in the
#: demo (the host emulation below must score identically to the on-core check).
KERNEL_NODE_OPTIMA = {MixedDagBase: 2.0, MixedDagTop: 4.0}
KERNEL_NODES = list(KERNEL_NODE_OPTIMA)


@pytest.fixture(autouse=True)
def _clear_dag():
    # The DAG dependency map is a module global; clear it so each build starts
    # from a clean graph and does not reuse a previous test's dependency nodes.
    gc.collect()
    dag._dependency_map.clear()
    yield
    dag._dependency_map.clear()


def _arm(cal):
    """Run every node's host_setup, as the client does before seeding a pool."""
    for node in dag.get_dependencies(cal):
        node.host_setup()


def _assert_no_subkernels(node, kernel_fn):
    embedding_map = node.core.compile(kernel_fn, (), {})[0]
    assert embedding_map.subkernels() == {}, (
        f"{type(node).__name__}: {kernel_fn.__name__} has subkernels; background "
        "precompilation is not thread-safe for it"
    )


# --------------------------------------------------------------------------- #
# Compile coverage
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cal_class", KERNEL_NODES, ids=[c.__name__ for c in KERNEL_NODES]
)
def test_kernel_node_check_compiles_without_subkernels(cal_class, fragment_factory):
    cal = fragment_factory(cal_class)
    assert is_kernel(cal.check_own_state)
    cal.host_setup()
    cal.core.precompile(cal.check_own_state)
    _assert_no_subkernels(cal, cal.check_own_state)


@pytest.mark.parametrize(
    "cal_class", KERNEL_NODES, ids=[c.__name__ for c in KERNEL_NODES]
)
def test_kernel_node_optimizer_loop_compiles_without_subkernels(
    cal_class, fragment_factory
):
    cal = fragment_factory(cal_class)
    cal.host_setup()
    # Bind the persistent stores exactly as the pool does before precompiling the
    # resident optimizer loop (both it and the check embed the same live stores).
    cal._kopt_bind_stores()
    cal.core.precompile(cal._optimizer_kernel_loop)
    _assert_no_subkernels(cal, cal._optimizer_kernel_loop)


def test_host_node_is_pure_host(fragment_factory):
    cal = fragment_factory(MixedDagMid)
    assert not is_kernel(cal.check_own_state), (
        "MixedDagMid.check_own_state must stay a host check so the walk exercises "
        "the direct (non-pooled) fallback path"
    )
    assert not is_kernel(cal.fix_own_state)
    assert not hasattr(cal, "core"), "the host-only node must not claim a core device"


def test_client_main_kernel_compiles(fragment_precompiler):
    # Fuses device_setup/run_once/device_cleanup into one kernel, as production's
    # _FragmentRunner does; run_once calls recalibrate_if_needed across the RPC.
    fragment_precompiler(QbutlerMixedDagFixDemoFrag)


def test_demo_in_compile_all_collection():
    from tests.test_compile_all import all_exp_fragments

    collected = {exp.__name__ for _, exp in all_exp_fragments}
    assert "QbutlerMixedDagFixDemoFrag" in collected
    assert issubclass(QbutlerMixedDagFixDemoFrag, ExpFragment)


# --------------------------------------------------------------------------- #
# Dispatch seam: kernel nodes -> pool, host node -> direct host call
# --------------------------------------------------------------------------- #


class _RecordingPool:
    """Records what gets seeded and fetched; hands back a trivially-OK stub for
    any kernel it is asked for (this half of the suite never runs a real walk)."""

    def __init__(self):
        self.seeded = {}
        self.fetched = []

    def seed(self, key, fn, *args, **kwargs):
        self.seeded.setdefault(key, fn)

    def get(self, key):
        self.fetched.append(key)
        return lambda: (CalibrationResult.OK, 10.0)

    def is_ready(self, key):
        return True

    def drain(self):
        pass

    def shutdown(self, wait=True):
        pass


def test_seeding_pools_kernel_nodes_not_host_node(fragment_factory):
    top = fragment_factory(MixedDagTop)
    _arm(top)
    pool = _RecordingPool()
    top.seed_precompile_pool(pool)

    by_type = {type(n): n for n in dag.get_dependencies(top)}
    for cal_class in KERNEL_NODES:
        node = by_type[cal_class]
        assert node._precompile_check_key == (node, "check")
        assert node._precompile_fix_key == (node, "fix")
        assert node._precompile_check_key in pool.seeded
        assert node._precompile_fix_key in pool.seeded

    mid = by_type[MixedDagMid]
    assert mid._precompile_check_key is None
    assert mid._precompile_fix_key is None
    assert mid._precompile_fix_own_key is None
    assert not any(key[0] is mid for key in pool.seeded), (
        "the host-only node must not be seeded into the precompile pool"
    )
    # The pool is still armed on the host node -- the fallback is check_key being
    # None, not the pool being absent (that is the real client's arrangement).
    assert mid._precompile_pool is pool


def test_check_dispatch_kernel_via_pool_host_direct(fragment_factory):
    top = fragment_factory(MixedDagTop)
    _arm(top)
    pool = _RecordingPool()
    top.seed_precompile_pool(pool)
    by_type = {type(n): n for n in dag.get_dependencies(top)}

    base = by_type[MixedDagBase]
    base._do_check_own_state()
    assert (base, "check") in pool.fetched, "kernel node must dispatch via the pool"

    mid = by_type[MixedDagMid]
    result, data = mid._do_check_own_state()
    assert not any(key[0] is mid for key in pool.fetched), (
        "host node must bypass the pool"
    )
    # A real host measurement ran (default mid_param=3.0 -> 10-|3-6|=7.0), not the
    # pool's (OK, 10.0) stub -- proof the direct fallback executed.
    assert result == CalibrationResult.BAD_DATA
    assert data == pytest.approx(7.0)


# --------------------------------------------------------------------------- #
# Full mixed walk (host-emulated kernel measurement)
# --------------------------------------------------------------------------- #


def _emulate_check(node):
    """Host stand-in for a kernel node's on-core parabola check: score the
    current committed param exactly as the @kernel check does."""
    optimum = KERNEL_NODE_OPTIMA[type(node)]
    p = node._kopt_stores[0].get_value()
    data = 10.0 - abs(p - optimum)
    result = CalibrationResult.OK if data > OK_SCORE else CalibrationResult.BAD_DATA
    return result, data


def _emulate_optimizer_loop(node):
    """Host mirror of Calibration._optimizer_kernel_loop: drive the real resident
    optimizer RPC protocol, taking each measurement on the host."""
    values = node._kopt_first_point()
    while len(values) > 0:
        for i in range(len(node._kopt_stores)):
            node._kopt_stores[i].set_value(values[i])
        result, data = _emulate_check(node)
        values = node._kopt_next_point(result, data)

    values = node._kopt_get_best()
    if len(values) > 0:
        for i in range(len(node._kopt_stores)):
            node._kopt_stores[i].set_value(values[i])
        result, data = _emulate_check(node)
        node._kopt_record_verify(result, data)


class _HostEmulatingPool:
    """Stands in for PrecompilePool: hands back callables that run the real walk
    protocol with the on-core measurement emulated on the host. Only the kernel
    nodes are ever seeded/fetched; the host node never reaches this pool."""

    def __init__(self):
        self.seeded = {}
        self.fetched = []

    def seed(self, key, fn, *args, **kwargs):
        self.seeded.setdefault(key, fn)

    def get(self, key):
        self.fetched.append(key)
        node, kind = key
        if kind == "check":
            return lambda: _emulate_check(node)
        if kind == "fix":
            return lambda: _emulate_optimizer_loop(node)
        raise KeyError(key)

    def is_ready(self, key):
        return key in self.seeded

    def drain(self):
        pass

    def shutdown(self, wait=True):
        pass


def _committed(node, attr):
    return getattr(node, attr).get()


def test_mixed_walk_fixes_all_nodes_base_first(fragment_factory):
    top = fragment_factory(MixedDagTop)
    _arm(top)
    pool = _HostEmulatingPool()
    top.seed_precompile_pool(pool)
    by_type = {type(n): n for n in dag.get_dependencies(top)}

    fix_order = []
    for node in dag.get_dependencies(top):
        original = node._do_fix_own_state

        def _record(_node=node, _orig=original):
            fix_order.append(type(_node).__name__)
            return _orig()

        node._do_fix_own_state = _record

    assert top.check_state(force=True)[0] != CalibrationResult.OK
    top.fix_state()
    assert top.check_state(force=True)[0] == CalibrationResult.OK

    assert fix_order == ["MixedDagBase", "MixedDagMid", "MixedDagTop"]

    assert _committed(by_type[MixedDagBase], "base_param") == pytest.approx(2.0)
    assert _committed(by_type[MixedDagMid], "mid_param") == pytest.approx(6.0)
    assert _committed(by_type[MixedDagTop], "top_param") == pytest.approx(4.0)

    # The host node was fixed without ever touching the pool.
    assert not any(key[0] is by_type[MixedDagMid] for key in pool.fetched)


def test_client_escape_walk_reenter_completes(fragment_factory):
    top = fragment_factory(MixedDagTop)
    _arm(top)
    pool = _HostEmulatingPool()
    top.seed_precompile_pool(pool)

    attempts = []

    def main():
        attempts.append(len(attempts))
        if top.check_state()[0] != CalibrationResult.OK:
            raise CalibrationEscape("a dependency needs recalibrating")

    drive_with_recalibration(main, top.fix_state, max_recalibrations=5, describe=" test")

    assert attempts == [0, 1], "escape once, fix the DAG, then re-enter and complete"
    assert top.check_state()[0] == CalibrationResult.OK
