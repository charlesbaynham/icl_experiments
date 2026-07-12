"""Client that keeps the XODT imaging check (and its MOT chain) healthy.

SingleXODTCalibration is check-only: if the XODT itself reads BAD the escape
walk cannot optimize it (no optimizable params) and surfaces the failure; the
nodes it depends on (blue MOT -> red MOT) are fixed as usual. A ``@kernel
run_once`` calls ``recalibrate_if_needed()`` and escapes to the host when the
chain has drifted.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.xodt_calibration import SingleXODTCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureXODTFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(SingleXODTCalibration)
        self.SingleXODTCalibration: SingleXODTCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureXODT = make_calibrated_experiment(EnsureXODTFrag)
