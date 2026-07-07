"""Compile-only coverage for the calibrations' kernel ``check_own_state``.

``test_compile_all`` only compiles ``device_setup``/``run_once``/``device_cleanup``
(Calibration.run_once is host code), so it never compiles ``check_own_state``.
This test does: it builds each calibration and precompiles its kernel check. The
real ARTIQ compiler runs -- type-checking the on-core param copy, the RPC call
sites, and the measurement it drives -- but the kernel is never executed, so no
camera or RPC fires.

A passing compile also proves the eager hardware store exists at compile time: the
kernel embeds a reference to it, so a missing store fails to compile.
"""

import gc

import pytest
from qbutler import dag

from repository.lib.calibrations.blue_mot import BlueMOTCalibration
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.lib.calibrations.rabi_pi_time import RabiDownPiTimeCalibration
from repository.lib.calibrations.rabi_pi_time import RabiUpPiTimeCalibration
from repository.lib.calibrations.red_mot import RedMOTCalibration

CALIBRATIONS = [
    BlueMOTCalibration,
    RedMOTCalibration,
    ClockDeliveryAOMCalibration,
    RabiUpPiTimeCalibration,
    RabiDownPiTimeCalibration,
]


@pytest.fixture(autouse=True)
def _clear_dag():
    # The DAG dependency map is a module global; clear it so each build starts
    # from a clean graph and does not reuse a previous test's dependency nodes.
    gc.collect()
    dag._dependency_map.clear()
    yield
    dag._dependency_map.clear()


@pytest.mark.parametrize(
    "cal_class", CALIBRATIONS, ids=[c.__name__ for c in CALIBRATIONS]
)
def test_check_own_state_compiles(cal_class, fragment_factory):
    cal = fragment_factory(cal_class)
    assert hasattr(cal.check_own_state, "artiq_embedded"), (
        f"{cal_class.__name__}.check_own_state must be a @kernel so the default "
        "grid-search optimizer sweep runs in a single kernel call"
    )
    # host_setup arms the (mocked) measurement, populating the kernel_invariant
    # attributes its device_setup/run_once read; ndscan runs it before the kernel.
    cal.host_setup()
    cal.core.precompile(cal.check_own_state)
