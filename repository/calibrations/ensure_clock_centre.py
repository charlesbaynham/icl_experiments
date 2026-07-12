"""Top-level client for the whole blue-MOT-to-clock calibration chain.

Fixing the delivery node walks the whole chain furthest-first
(blue MOT -> red MOT -> coarse clock centre -> refined clock centre),
re-measuring only stale nodes. A ``@kernel run_once`` calls
``recalibrate_if_needed()`` and escapes to the host when any node has drifted;
within every node's timeout a re-entry does nothing (state recalled from the
calibrations.status dataset).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)


class EnsureClockCentreFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()


EnsureClockCentre = make_calibrated_experiment(EnsureClockCentreFrag)
