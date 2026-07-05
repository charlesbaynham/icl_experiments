"""Client for the clock delivery-AOM centring calibration alone: check, fix."""

import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration

logger = logging.getLogger(__name__)


class EnsureClockDeliveryFrag(ExpFragment):
    def build_fragment(self):
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
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Clock delivery not OK after fix_state: {result}")


EnsureClockDelivery = make_fragment_scan_exp(EnsureClockDeliveryFrag)
