"""Top-level client for the whole blue-MOT-to-clock calibration chain.

Running this proves the connected qbutler DAG contract end to end: fixing the
refined clock-centre node walks the whole chain furthest-first
(blue MOT -> red MOT -> coarse clock centre -> refined clock centre),
re-measuring only stale nodes, before the client proceeds. Within every node's
timeout a re-submission does nothing at all (state recalled from the
calibrations.status dataset).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from artiq.master.worker_impl import CCB
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration

logger = logging.getLogger(__name__)

DAG_APPLET_CMD = (
    "${python} -m repository.lib.applets.qbutler_dag_applet "
    "calibrations.dag calibrations.status"
)


class EnsureClockCentreFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize the whole chain unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

        self.setattr_device("ccb")
        self.ccb: CCB

    def host_setup(self):
        super().host_setup()
        self.ccb.issue("create_applet", "Calibration DAG", DAG_APPLET_CMD)

    @kernel
    def run_once(self):
        self.ClockDeliveryAOMCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.ClockDeliveryAOMCalibration.check_state()
        logger.info("Clock centre chain state: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError("Clock centre chain not OK after fix_state")


EnsureClockCentre = make_fragment_scan_exp(EnsureClockCentreFrag)
