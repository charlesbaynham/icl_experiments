import logging
import time

from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import TerminationRequested
from koheron_ctl200_laser_driver import CTL200
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from toptica.lasersdk.dlcpro.v1_9_0 import DLCpro
from toptica_wrapper.driver import TopticaDLCPro


class _MonitorToptica(Calibration):
    """
    LogTopticaLaser

    Logs the voltage, current, temperature of a Toptica DLCPro laser
    """

    dlcpro_name: str = None  # Name of the DLCPro in the device_db

    def __init__(self, *args, **kwargs):
        if self.dlcpro_name is None:
            raise NotImplementedError(
                "You must subclass this interface class and set cls.laser_device_name"
            )

        super().__init__(*args, **kwargs)

    def build_calibration(self):
        self.dlcpro: TopticaDLCPro = self.get_device(self.dlcpro_name)
        self.raw_dlcpro = self.dlcpro.get_dlcpro()

        self.set_timeout(10)

    def host_setup(self):
        super().host_setup()

        # Open a connection
        self.raw_dlcpro.open()

        # Save the laser
        self.laser = self.dlcpro.get_laser()

    def host_cleanup(self):
        self.raw_dlcpro.close()

        super().host_cleanup()

    def check_own_state(self):
        out = {}

        try:
            out["voltage_setpoint"] = self.laser.dl.pc.voltage_set.get()
            out["voltage_actual"] = self.laser.dl.pc.voltage_act.get()
            out["current_setpoint"] = self.laser.dl.cc.current_set.get()
            out["current_actual"] = self.laser.dl.cc.current_act.get()
            out["temperature_setpoint"] = self.laser.dl.tc.temp_set.get()
            out["temperature_actual"] = self.laser.dl.tc.temp_act.get()

            result = CalibrationResult.OK

        except AttributeError:
            # The connection to the controller failed
            out["status"] = "ERROR"
            result = CalibrationResult.BAD_DATA

        return result, {
            "tags": {
                "device": self.dlcpro_name,
                "parent": _MonitorToptica.__name__,
            },
            "fields": out,
        }
