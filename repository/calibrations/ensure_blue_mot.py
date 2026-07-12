"""Client for the blue-MOT calibration: keep it healthy while the kernel runs.

The working demo of the escape protocol: a ``@kernel run_once`` calls
``recalibrate_if_needed()`` at a safe point; if the blue MOT (or anything it
depends on) has drifted the kernel escapes to the host, which re-optimizes it
through the precompiled per-node kernels and re-enters in ~0.24 s.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.blue_mot import BlueMOTCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureBlueMOTFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(BlueMOTCalibration)
        self.BlueMOTCalibration: BlueMOTCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureBlueMOT = make_calibrated_experiment(EnsureBlueMOTFrag)
