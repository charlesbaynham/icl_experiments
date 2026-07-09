"""Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

Three demos:
- ``KernelDemoCalibration``: ``@kernel check_own_state`` — compiles, owns the
  timeline, returns ``(CalibrationResult, float)`` through the RPC boundary.
- ``KernelFixDemoCalibration``: host check that fails until the ``@kernel``
  ``fix_own_state`` has run (device-side repair demo).
- ``QbutlerKernelDagFixDemo``: the headline — a ``@kernel run_once`` fixes a
  3-deep calibration DAG (synthetic parabola "measurements", all levels
  initially broken) from within a **single kernel**: one compile + one
  upload for the whole fix, each optimizer walking on the host and streaming
  points into the resident kernel over RPC. Watch the worker log for exactly
  one compile bump and the ``QB_DAG_FIX`` result line.
"""

import logging
import time

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: recompiling and re-running the kernel demos back-to-back.
IDLE_SLEEP_S = 30.0


class KernelDemoCalibration(Calibration):
    """Trivially-healthy calibration whose check runs on the core device."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(300.0)

    @kernel
    def check_own_state(self):
        self.core.break_realtime()
        delay(1e-3)
        return CalibrationResult.OK, 0.0


class KernelFixDemoCalibration(Calibration):
    """Fails its host-side check until the kernel fix has run."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(300.0)
        self._fixed = False

    def check_own_state(self):
        if self._fixed:
            return CalibrationResult.OK, 1.0
        return CalibrationResult.BAD_DATA, 0.0

    @kernel
    def fix_own_state(self):
        self.core.break_realtime()
        delay(1e-3)
        self._mark_fixed()

    @rpc
    def _mark_fixed(self):
        self._fixed = True


class QbutlerKernelDemoFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_calibration(KernelDemoCalibration)
        self.KernelDemoCalibration: KernelDemoCalibration
        self.setattr_calibration(KernelFixDemoCalibration)
        self.KernelFixDemoCalibration: KernelFixDemoCalibration

    def run_once(self):
        result, data = self.KernelDemoCalibration.check_state(force=True)
        logger.info("KernelDemoCalibration check: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Kernel check demo failed: {result}")

        self.KernelFixDemoCalibration.fix_state(force=True)
        result, data = self.KernelFixDemoCalibration.check_state()
        logger.info(
            "KernelFixDemoCalibration after kernel fix: %s (data=%s)", result, data
        )
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Kernel fix demo failed: {result}")

        time.sleep(IDLE_SLEEP_S)


QbutlerKernelDemo = make_fragment_scan_exp(QbutlerKernelDemoFrag)


class KernelDagDemoBase(Calibration):
    """Deepest level of the 3-deep kernel DAG demo. Synthetic parabola
    measurement computed on-core; optimum at 2.0, default 5.0 (broken until
    fixed — the OK window excludes the default)."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(300.0)
        self.setattr_param_optimizable(
            "base_param", "Base param", min=0.0, max=10.0, default=5.0
        )

    @kernel
    def check_own_state(self):
        self.core.break_realtime()
        delay(1e-3)
        p = self.base_param.get()
        data = 10.0 - abs(p - 2.0)
        if data > 9.5:
            return CalibrationResult.OK, data
        else:
            return CalibrationResult.BAD_DATA, data


class KernelDagDemoMid(Calibration):
    """Middle level; depends on KernelDagDemoBase. Optimum at 7.0."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(300.0)
        self.add_dependency(KernelDagDemoBase)
        self.setattr_param_optimizable(
            "mid_param", "Mid param", min=0.0, max=10.0, default=3.0
        )

    @kernel
    def check_own_state(self):
        self.core.break_realtime()
        delay(1e-3)
        p = self.mid_param.get()
        data = 10.0 - abs(p - 7.0)
        if data > 9.5:
            return CalibrationResult.OK, data
        else:
            return CalibrationResult.BAD_DATA, data


class KernelDagDemoTop(Calibration):
    """Top level; depends on KernelDagDemoMid. Optimum at 4.0."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(300.0)
        self.add_dependency(KernelDagDemoMid)
        self.setattr_param_optimizable(
            "top_param", "Top param", min=0.0, max=10.0, default=8.0
        )

    @kernel
    def check_own_state(self):
        self.core.break_realtime()
        delay(1e-3)
        p = self.top_param.get()
        data = 10.0 - abs(p - 4.0)
        if data > 9.5:
            return CalibrationResult.OK, data
        else:
            return CalibrationResult.BAD_DATA, data


class QbutlerKernelDagFixDemoFrag(ExpFragment):
    """Fix the whole 3-deep DAG from a @kernel run_once in one kernel call."""

    def build_fragment(self):
        self.setattr_calibration(KernelDagDemoTop)
        self.KernelDagDemoTop: KernelDagDemoTop
        self.setattr_device("core")
        self.core: Core

    def host_setup(self):
        super().host_setup()
        # Generate the kernel DAG-fix driver before run_once is compiled.
        self.KernelDagDemoTop.prepare_kernel_fix()
        self._t_start = time.time()

    @kernel
    def run_once(self):
        ok = self.KernelDagDemoTop.fix_state_kernel(False)
        self._report(ok)

    def _report(self, ok) -> None:
        # WARNING so it survives log filtering and is greppable by RID.
        logger.warning(
            "QB_DAG_FIX ok=%s dt=%.2fs (one kernel call for the whole 3-level fix)",
            ok,
            time.time() - self._t_start,
        )
        if not ok:
            logger.error(
                "Kernel DAG fix failed: %s",
                self.KernelDagDemoTop._fsk_failure,
            )
        time.sleep(IDLE_SLEEP_S)


QbutlerKernelDagFixDemo = make_fragment_scan_exp(QbutlerKernelDagFixDemoFrag)
