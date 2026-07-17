"""Record qbutler recalibrations to the lab InfluxDB.

qbutler is deliberately influx-agnostic: its ``Calibration`` base exposes a
no-op ``_on_recalibrated`` hook that fires whenever a fix commits new optimal
parameters. This mix-in implements that hook against the ARTIQ ``influx_logger``
controller -- the same best-effort interface the database monitors use -- so the
influx dependency lives here in icl_experiments and never in qbutler.

Add it to the left of ``Calibration`` in a calibration's bases::

    class MyCalibration(InfluxRecalibrationLogMixin, Calibration):
        ...

The controller is ``best_effort``, so if influx is down the point is dropped
silently; the write is also wrapped by qbutler's hook dispatcher, so logging can
never turn a good calibration into a failure.
"""

import logging

from artiq_influx_generic import InfluxController

from qbutler.calibration import Calibration

logger = logging.getLogger(__name__)


class InfluxRecalibrationLogMixin(Calibration):
    def build_fragment(self, *args, **kwargs):
        super().build_fragment(*args, **kwargs)
        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

    def _on_recalibrated(self, committed_params):
        fields = {name: float(value) for name, value in committed_params.items()}
        self.influx_logger.write(
            tags={
                "type": "calibration",
                "calibration": self.__class__.__name__,
                "experiment": "aion",
            },
            fields=fields,
        )
        logger.info(
            "Logged recalibration of %s to influx: %s",
            self.__class__.__name__,
            fields,
        )
