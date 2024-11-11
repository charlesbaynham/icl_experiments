import logging

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from relocker_driver.aqctl_relocker_driver import RelockerDriver

logger = logging.getLogger(__name__)


class _MonitorRelocker(Calibration):
    """
    Monitor for a relocker board for the Koheron-controlled IJDs, connected via USB

    Must be subclassed for the appropriate controller with `cls.controller_name`
    set to an entry in the device_db.
    """

    board_name: str = None
    channel: int = None

    def __init__(self, *args, **kwargs):
        if self.controller_name is None or self.channel is None:
            raise NotImplementedError(
                "You must subclass this interface class and set cls.board_name and cls.channel"
            )

        super().__init__(*args, **kwargs)

    def build_calibration(self):
        self.board: RelockerDriver = self.get_device(self.board_name)
        self.set_timeout(10)

    def check_own_state(self):
        out = {}

        try:
            self.controller.ping()

            result = self.board.get_result(self.channel)
            auto_stats = self.board.get_auto_stats(self.channel)
            self.board.get_scan_voltages(self.channel)
            auto_relocking = self.board.get_auto(self.channel)

            out["number_autos"] = auto_stats[0]
            out["number_autos_succeeded"] = auto_stats[1]
            out["status"] = "AUTO ON" if auto_relocking else "AUTO OFF"
            result = CalibrationResult.OK

        except AttributeError:
            # The connection to the controller failed
            out["status"] = "ERROR"
            result = CalibrationResult.BAD_DATA

        return result, {
            "tags": {
                "device": self.board_name,
                "channel": self.channel,
                "parent": _MonitorRelocker.__name__,
            },
            "fields": out,
        }


class MonitorBlueIJD1Relocker(_MonitorRelocker):
    board_name = "blue_relocker"
    channel = 0


class MonitorBlueIJD2Relocker(_MonitorRelocker):
    board_name = "blue_relocker"
    channel = 1


class MonitorBlueIJD3Relocker(_MonitorRelocker):
    board_name = "blue_relocker"
    channel = 2


class MonitorRedIJD1Relocker(_MonitorRelocker):
    board_name = "red_IJD1_relocker"
    channel = 0
