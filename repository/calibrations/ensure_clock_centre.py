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
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration

logger = logging.getLogger(__name__)


class EnsureClockCentreFrag(CalibratedExpFragment):
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

    @kernel
    def run_once(self):
        self.recalibrate_if_needed(force=self.force_recalibrate.get())


EnsureClockCentre = make_calibrated_experiment(EnsureClockCentreFrag)
