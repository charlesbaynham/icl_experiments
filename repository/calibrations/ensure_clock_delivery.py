"""Client for the clock delivery-AOM centring calibration alone: check, fix."""

import logging
import time

from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureClockDeliveryFrag(CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()
        self.setattr_calibration(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    def run_once(self):
        self.ClockDeliveryAOMCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.ClockDeliveryAOMCalibration.check_state()
        logger.info("Clock delivery state: %s (data=%s)", result, data)
        logger.info("Sleeping for %.0fs...", IDLE_SLEEP_S)

        if result != CalibrationResult.OK:
            raise RuntimeError(f"Clock delivery not OK after fix_state: {result}")

        time.sleep(IDLE_SLEEP_S)


EnsureClockDelivery = make_fragment_scan_exp(EnsureClockDeliveryFrag)
