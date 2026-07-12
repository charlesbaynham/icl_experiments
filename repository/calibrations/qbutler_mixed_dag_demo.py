"""Prove the precompiled-calibration walk handles a MIXED-mode DAG.

The headline case the kernel demo does not cover: a dependency chain that
*alternates* between calibrations whose ``check_own_state`` runs on the core
device (pooled precompiled kernels) and one whose check is plain host Python
(no hardware at all). The host-only node must fall back to running its
``check_own_state``/``fix_own_state`` directly instead of through the
:class:`~qbutler.precompile.PrecompilePool`, so the escape -> walk -> fix ->
re-enter cycle spans both dispatch paths in a single run.

Chain (top attaches down to base):

    MixedDagTop   (kernel check, optimum 4.0)
      -> MixedDagMid   (HOST-ONLY check, pure Python, optimum 6.0)
           -> MixedDagBase (kernel check, optimum 2.0)

Every node is a synthetic parabola "measurement" broken at its default, so a
live run escapes once, walks base-first fixing every level -- the two kernel
nodes through pooled optimizer kernels, the host node through the ordinary host
optimizer -- and re-enters the (precompiled) client kernel. Watch the worker log
for the escape line, one compile bump per *kernel* node, and no compile for the
host node.
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
#: re-running the demo back-to-back.
IDLE_SLEEP_S = 10.0

#: A synthetic check is OK only when its parabola score clears this. The optimum
#: scores 10.0; the nearest grid neighbour scores 9.0, so only the exact optimum
#: (which the 11-point [0, 10] grid hits) passes -- the node is genuinely broken
#: until fixed. Mirrored by the mixed-DAG test's host emulation.
OK_SCORE = 9.5


class MixedDagBase(Calibration):
    """Deepest level: a @kernel parabola check. Optimum 2.0, default 5.0."""

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
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1e-3)
        )
        p = self.base_param.get()
        data = 10.0 - abs(p - 2.0)
        if data > OK_SCORE:
            return CalibrationResult.OK, data
        return CalibrationResult.BAD_DATA, data


class MixedDagMid(Calibration):
    """Middle level, host-only: ``check_own_state`` is plain Python that touches
    no hardware (no ``core`` device), so the walk must run it directly rather
    than through the precompiled-kernel pool. Depends on MixedDagBase; optimum
    6.0, default 3.0. Stands in for a software setpoint / dataset-derived check.
    """

    def build_calibration(self):
        self.set_timeout(300.0)
        self.add_dependency(MixedDagBase)
        self.setattr_param_optimizable(
            "mid_param", "Mid param", min=0.0, max=10.0, default=3.0
        )
        self.mid_param: FloatParamHandle

    def check_own_state(self):
        p = self.mid_param.get()
        data = 10.0 - abs(p - 6.0)
        logger.info("MixedDagMid host check: param=%s data=%s", p, data)
        if data > OK_SCORE:
            return CalibrationResult.OK, data
        return CalibrationResult.BAD_DATA, data


class MixedDagTop(Calibration):
    """Top level: a @kernel parabola check. Depends on MixedDagMid; optimum 4.0,
    default 8.0."""

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core
        self.set_timeout(150.0)
        self.add_dependency(MixedDagMid)
        self.setattr_param_optimizable(
            "top_param", "Top param", min=0.0, max=10.0, default=8.0
        )
        self.top_param: FloatParamHandle

    @kernel
    def check_own_state(self):
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1e-3)
        )
        p = self.top_param.get()
        data = 10.0 - abs(p - 4.0)
        if data > OK_SCORE:
            return CalibrationResult.OK, data
        return CalibrationResult.BAD_DATA, data


class QbutlerMixedDagFixDemoFrag(CalibratedExpFragment):
    """Fix a mixed kernel/host DAG via the escape protocol: the kernel escapes
    once, the host walks base-first fixing every node -- the two kernel nodes
    through pooled optimizer kernels, the host node through the host optimizer
    (the RPC-style fallback) -- then re-enters the (precompiled) kernel."""

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_calibration(MixedDagTop)
        self.MixedDagTop: MixedDagTop

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


QbutlerMixedDagFixDemo = make_calibrated_experiment(QbutlerMixedDagFixDemoFrag)
