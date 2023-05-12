import logging

from koheron_ctl200_laser_driver import CTL200
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


class MonitorIJD1(Calibration):
    def build_calibration(self):
        self.setattr_device("blue_IJD1_controller")

        self.controller: CTL200 = self.blue_IJD1_controller

        self.set_timeout(30)

    def check_own_state(self):
        out = {}

        out["temperature_actual"] = self.controller.get_temperature_actual()
        out["temperature_setpoint"] = self.controller.get_temperature_setpoint()
        out["current"] = 1e-3 * self.controller.get_current_mA()
        out["voltage"] = self.controller.get_voltage()
        out["status"] = "ON" if self.controller.status() else "OFF"

        result = CalibrationResult.OK if out["status"] else CalibrationResult.BAD_DATA

        return result, {
            "tags": {"device": "blue_IJD1_controller"},
            "fields": out,
        }
