import logging

from artiq_influx_generic import InfluxController
from monitor_weather import MonitorWeather
from qbutler.monitoring import make_monitor_controller

logger = logging.getLogger(__name__)


def my_db_logger(self, name, state, data):
    l: InfluxController = self.influx_logger
    # l.write(something)

    assert l

    print("(not writing to db) {} - {} - {}".format(name, state, data))


MyMonitorMaster = make_monitor_controller(
    "MyMonitorMaster", monitors=[MonitorWeather], devices=["influx_logger"]
)
