import logging

import requests
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)


class _MonitorLabTemperature(Calibration):
    """
    Monitor the temperature of the lab
    """

    monitor_url = None
    description = None

    def temperature_string_parser(self, temperature_string):
        return float(temperature_string)

    def __init__(self, managers_or_parent, *args, **kwargs):
        if self.monitor_url is None or self.description is None:
            raise NotImplementedError(
                "You must subclass this class and define 'monitor_url' and 'description"
            )

        super().__init__(managers_or_parent, *args, **kwargs)

    def build_calibration(self):
        self.set_timeout(30)

    def check_own_state(self):
        temp_str = requests.get(self.monitor_url).text
        temperature = self.temperature_string_parser(temp_str)

        logger.debug('Temperature = %f ("%s")', temperature, temp_str)

        return CalibrationResult.OK, {
            "tags": {"sensor": self.description, "type": "temperature"},
            "fields": {"value": temperature},
        }


class MonitorTemperatureSidearm(_MonitorLabTemperature):
    monitor_url = "http://temperature-nano1.lan/temp1.txt"
    description = "above_chamber"


class MonitorTemperatureDencoOut(_MonitorLabTemperature):
    monitor_url = "http://temperature-nano2.lan/temp1.txt"
    description = "denco_out"


class MonitorTemperatureDencoIn(_MonitorLabTemperature):
    monitor_url = "http://temperature-nano3.lan/temp1.txt"
    description = "denco_in"


class _InveoNanoThermocoupleMonitor(_MonitorLabTemperature):
    """
    The Inveo NANO-TC-SENSOR has a slightly different interface, so subclass for it here
    """

    def temperature_string_parser(self, xml_string):
        """
        Parse the XML status string from the Inveo NANO-TC-SENSOR
        """
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_string)
        temp_str = root.find("valFinal0").text
        return float(temp_str)


class MonitorTemperaturePCW(_InveoNanoThermocoupleMonitor):
    monitor_url = "http://temperature-nano-thermocouple-1.lan/status.xml"
    description = "PCW"
