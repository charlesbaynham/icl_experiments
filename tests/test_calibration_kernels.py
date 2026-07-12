"""Compile-only coverage for the calibrations' precompiled kernels.

``test_compile_all`` only compiles ``device_setup``/``run_once``/``device_cleanup``
(Calibration.run_once is host code), so it never compiles the kernels the
precompiled-calibration pool relies on. This test does, for all seven production
calibrations plus the synthetic DAG demo:

- the per-node ``@kernel check_own_state`` (five MOT/clock cals + XODT + demos);
- the resident ``_optimizer_kernel_loop`` for every default-optimizer node (the
  kernel the pool precompiles as that node's fix);
- the coarse node's ``@kernel _measure`` (its check is host, driving this
  kernel), which the pool precompiles instead of a check kernel.

Each precompiled artifact is asserted subkernel-free: the background compile
thread is only thread-safe against a running kernel when the kernel has no
subkernels (``Core.precompile``'s compile path touches no ``comm`` state then).

The real ARTIQ compiler runs -- type-checking the on-core param copy, the RPC
call sites and the measurement each kernel drives -- but nothing is executed, so
no camera or RPC fires.
"""

import gc

import pytest
from ndscan.experiment.utils import is_kernel

from qbutler import dag
from repository.calibrations.qbutler_kernel_demo import KernelDagDemoBase
from repository.calibrations.qbutler_kernel_demo import KernelDagDemoMid
from repository.calibrations.qbutler_kernel_demo import KernelDagDemoTop
from repository.lib.calibrations.blue_mot import BlueMOTCalibration
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.lib.calibrations.coarse_clock_centre import CoarseClockCentreCalibration
from repository.lib.calibrations.rabi_pi_time import RabiDownPiTimeCalibration
from repository.lib.calibrations.rabi_pi_time import RabiUpPiTimeCalibration
from repository.lib.calibrations.red_mot import RedMOTCalibration
from repository.lib.calibrations.xodt_calibration import SingleXODTCalibration

#: Calibrations whose ``check_own_state`` runs on the core device (the pool
#: precompiles the check itself). XODT is check-only; the rest also auto-fix.
KERNEL_CHECK_CALS = [
    BlueMOTCalibration,
    RedMOTCalibration,
    SingleXODTCalibration,
    ClockDeliveryAOMCalibration,
    RabiUpPiTimeCalibration,
    RabiDownPiTimeCalibration,
    KernelDagDemoBase,
    KernelDagDemoMid,
    KernelDagDemoTop,
]

#: Calibrations with a kernel check AND optimizable params: the pool precompiles
#: their resident optimizer loop as the fix (XODT is check-only, so absent).
OPTIMIZER_FIX_CALS = [
    BlueMOTCalibration,
    RedMOTCalibration,
    ClockDeliveryAOMCalibration,
    RabiUpPiTimeCalibration,
    RabiDownPiTimeCalibration,
    KernelDagDemoBase,
    KernelDagDemoMid,
    KernelDagDemoTop,
]


@pytest.fixture(autouse=True)
def _clear_dag():
    # The DAG dependency map is a module global; clear it so each build starts
    # from a clean graph and does not reuse a previous test's dependency nodes.
    gc.collect()
    dag._dependency_map.clear()
    yield
    dag._dependency_map.clear()


def _assert_no_subkernels(node, kernel_fn):
    """A precompiled artifact must have no subkernels or its background compile
    is not thread-safe against a concurrently running kernel."""
    embedding_map = node.core.compile(kernel_fn, (), {})[0]
    assert embedding_map.subkernels() == {}, (
        f"{type(node).__name__}: {kernel_fn.__name__} has subkernels; background "
        "precompilation is not thread-safe for it"
    )


@pytest.mark.parametrize(
    "cal_class", KERNEL_CHECK_CALS, ids=[c.__name__ for c in KERNEL_CHECK_CALS]
)
def test_check_kernel_compiles_without_subkernels(cal_class, fragment_factory):
    cal = fragment_factory(cal_class)
    assert is_kernel(cal.check_own_state), (
        f"{cal_class.__name__}.check_own_state must be a @kernel so the pool "
        "precompiles it as the per-node check"
    )
    # host_setup arms the (mocked) measurement, populating the attributes its
    # device_setup/run_once read; ndscan runs it before the kernel.
    cal.host_setup()
    cal.core.precompile(cal.check_own_state)
    _assert_no_subkernels(cal, cal.check_own_state)


@pytest.mark.parametrize(
    "cal_class", OPTIMIZER_FIX_CALS, ids=[c.__name__ for c in OPTIMIZER_FIX_CALS]
)
def test_optimizer_loop_compiles_without_subkernels(cal_class, fragment_factory):
    cal = fragment_factory(cal_class)
    cal.host_setup()
    # Bind the persistent stores exactly as the pool does before precompiling the
    # resident optimizer loop (both it and the check embed the same live stores).
    cal._kopt_bind_stores()
    cal.core.precompile(cal._optimizer_kernel_loop)
    _assert_no_subkernels(cal, cal._optimizer_kernel_loop)


def test_coarse_measure_compiles_without_subkernels(fragment_factory):
    """Coarse's check is host, driving a @kernel _measure; the pool precompiles
    _measure (not a check kernel) and the host averaging loop deploys it."""
    cal = fragment_factory(CoarseClockCentreCalibration)
    assert not is_kernel(cal.check_own_state), (
        "CoarseClockCentreCalibration.check_own_state is expected to stay a host "
        "check that drives the @kernel _measure"
    )
    assert is_kernel(cal._measure)
    cal.host_setup()
    cal.core.precompile(cal._measure)
    _assert_no_subkernels(cal, cal._measure)
