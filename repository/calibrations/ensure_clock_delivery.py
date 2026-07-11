"""Client for the clock delivery-AOM centring calibration alone: check, fix."""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
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
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    def host_setup(self):
        super().host_setup()
        # Build the kernel check/fix drivers before run_once is compiled.
        self.ClockDeliveryAOMCalibration.prepare_kernel_fix()

    @kernel
    def run_once(self):
        self.ClockDeliveryAOMCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.ClockDeliveryAOMCalibration.check_state()
        logger.info("Clock delivery state: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError("Clock delivery not OK after fix_state")

        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureClockDelivery = make_fragment_scan_exp(EnsureClockDeliveryFrag)
