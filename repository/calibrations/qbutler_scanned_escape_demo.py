"""Live dark-rig demo of the scanned-axes escape/resume path (WP-B).

The same 3-deep kernel DAG as :mod:`qbutler_kernel_demo` (parabola checks broken
at their defaults), but driven as an ndscan SCAN over a dummy axis. On the first
scan point the ``@kernel run_once``'s ``recalibrate_if_needed()`` finds the DAG
drifted and raises ``CalibrationEscape``; the host walks the fix (pooled per-node
optimizer kernels) and the scan RESUMES at that point — it re-runs and every
subsequent point runs straight through (the DAG is now within timeout). The
result dataset should therefore hold every scanned point exactly once, and the
worker log a single mid-scan escape line.

Submit with a scan over ``scan_index`` (e.g. linear 0..4, 5 points). No atoms,
no fields — pure on-core compute.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.calibrations.qbutler_kernel_demo import KernelDagDemoTop

logger = logging.getLogger(__name__)


class QbutlerScannedEscapeDemoFrag(CalibratedExpFragment):
    """Scan a dummy axis; escape+recalibrate at the first point, resume, and
    complete every point exactly once."""

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_param(
            "scan_index",
            FloatParam,
            description="Dummy scan axis",
            default=0.0,
            min=0.0,
            max=100.0,
        )
        self.scan_index: FloatParamHandle
        self.setattr_result("scanned_value", FloatChannel)
        self.scanned_value: FloatChannel
        self.setattr_calibration(KernelDagDemoTop)
        self.KernelDagDemoTop: KernelDagDemoTop

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        value = self.scan_index.get()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(0.2)
        )
        self.scanned_value.push(value)


QbutlerScannedEscapeDemo = make_calibrated_experiment(QbutlerScannedEscapeDemoFrag)
