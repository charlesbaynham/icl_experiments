"""Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

Two demos:
- ``KernelDemoCalibration``: ``@kernel check_own_state`` — compiles, owns the
  timeline, returns ``(CalibrationResult, float)`` through the RPC boundary.
- ``KernelFixDemoCalibration``: host check that fails until the ``@kernel``
  ``fix_own_state`` has run (device-side repair demo).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


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
        logger.info("KernelFixDemoCalibration after kernel fix: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Kernel fix demo failed: {result}")


QbutlerKernelDemo = make_fragment_scan_exp(QbutlerKernelDemoFrag)
