import logging

from qbutler.monitoring import make_monitor_controller

from .monitor_weather import MonitorWeather

logger = logging.getLogger(__name__)


# def my_db_logger(self, name, state, data):
#     self.my_db_driver.write(name, data)


MyMonitorMaster = make_monitor_controller(
    "MyMonitorMaster", monitors=[MonitorWeather]
)
