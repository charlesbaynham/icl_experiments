"""Client that keeps the red-MOT calibration chain healthy while it runs.

The escape protocol over the whole blue MOT -> red MOT chain: a ``@kernel
run_once`` calls ``recalibrate_if_needed()``; if anything in the chain has
drifted the kernel escapes, the host re-optimizes the stale nodes through the
precompiled per-node kernels, and re-enters. Within each node's timeout a
re-entry does nothing (state recalled from the calibrations.status dataset).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.red_mot import RedMOTCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureRedMOTFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureRedMOT = make_calibrated_experiment(EnsureRedMOTFrag)
