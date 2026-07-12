"""Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

Two runnable demos, both driven through the precompiled-calibration client
:class:`~qbutler.client.CalibratedExpFragment`:

- ``QbutlerKernelDemo``: ``recalibrate_if_needed()`` on a trivially-healthy
  ``@kernel check_own_state`` node — the happy path, so the kernel never escapes
  and runs straight through.
- ``QbutlerKernelDagFixDemo``: the headline — a ``@kernel run_once`` whose
  ``recalibrate_if_needed()`` finds a 3-deep DAG (synthetic parabola
  "measurements", every level broken at its default) drifted, escapes to the
  host, which fixes every level through the precompiled per-node optimizer
  kernels and re-enters in ~0.24 s. Watch the worker log for the escape line and
  one compile bump per node.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParamHandle

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: re-running the kernel demos back-to-back.
IDLE_SLEEP_S = 10.0


class KernelDemoCalibration(Calibration):
    """Trivially-healthy calibration whose check runs on the core device."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(100.0)

    @kernel
    def check_own_state(self):
        logger.info("KernelDemoCalibration check_own_state running on core")
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)
        )
        logger.info("KernelDemoCalibration check_own_state done waiting on core")
        return CalibrationResult.OK, 0.0


class QbutlerKernelDemoFrag(CalibratedExpFragment):
    """Happy-path escape demo: the single node is always OK, so
    ``recalibrate_if_needed()`` never raises and the kernel runs to completion."""

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_calibration(KernelDemoCalibration)
        self.KernelDemoCalibration: KernelDemoCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


QbutlerKernelDemo = make_calibrated_experiment(QbutlerKernelDemoFrag)


class KernelDagDemoBase(Calibration):
    """Deepest level of the 3-deep kernel DAG demo. Synthetic parabola
    measurement computed on-core; optimum at 2.0, default 5.0 (broken until
    fixed — the OK window excludes the default)."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(100.0)
        self.setattr_param_optimizable(
            "base_param", "Base param", min=0.0, max=10.0, default=5.0
        )
        self.base_param: FloatParamHandle

    @kernel
    def check_own_state(self):
        logger.info("KernelDagDemoBase check_own_state running on core")
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1e-3)
        )
        p = self.base_param.get()
        data = 10.0 - abs(p - 2.0)
        if data > 9.5:
            logger.info("KernelDagDemoBase check_own_state OK (data=%s)", data)
            return CalibrationResult.OK, data
        else:
            logger.info("KernelDagDemoBase check_own_state BAD_DATA (data=%s)", data)
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
        self.mid_param: FloatParamHandle

    @kernel
    def check_own_state(self):
        logger.info("KernelDagDemoMid check_own_state running on core")
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)
        )
        p = self.mid_param.get()
        data = 10.0 - abs(p - 7.0)
        if data > 9.5:
            logger.info("KernelDagDemoMid check_own_state OK (data=%s)", data)
            return CalibrationResult.OK, data
        else:
            logger.info("KernelDagDemoMid check_own_state BAD_DATA (data=%s)", data)
            return CalibrationResult.BAD_DATA, data


class KernelDagDemoTop(Calibration):
    """Top level; depends on KernelDagDemoMid. Optimum at 4.0."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(150.0)
        self.add_dependency(KernelDagDemoMid)
        self.setattr_param_optimizable(
            "top_param", "Top param", min=0.0, max=10.0, default=8.0
        )
        self.top_param: FloatParamHandle

    @kernel
    def check_own_state(self):
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)
        )
        p = self.top_param.get()
        data = 10.0 - abs(p - 4.0)
        if data > 9.5:
            return CalibrationResult.OK, data
        else:
            return CalibrationResult.BAD_DATA, data


class QbutlerKernelDagFixDemoFrag(CalibratedExpFragment):
    """Fix a whole 3-deep DAG via the escape protocol: the kernel escapes once,
    the host walks blue-first fixing every node through pooled optimizer kernels,
    then re-enters the (precompiled) kernel from the top."""

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_calibration(KernelDagDemoTop)
        self.KernelDagDemoTop: KernelDagDemoTop

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


QbutlerKernelDagFixDemo = make_calibrated_experiment(QbutlerKernelDagFixDemoFrag)
