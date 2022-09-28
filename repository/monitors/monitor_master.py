import logging

from artiq_influx_generic import InfluxController
from monitor_weather import MonitorWeather
from qbutler.monitoring import make_monitor_controller

logger = logging.getLogger(__name__)


def my_db_logger(self, name, state, data):

    if isinstance(data, dict):
        fields = data
    elif isinstance(data, float):
        fields = {"value": data}
    else:
        raise ValueError(
            "Data type %s not supported - only floats and dicts are accepted", data
        )

    logger.debug("Writing to database: type = %s, fields = %s", name, data)

    self.influx_logger: InfluxController
    self.influx_logger.write(
        tags={"type": name},
        fields=fields,
    )


MyMonitorMaster = make_monitor_controller(
    "MyMonitorMaster",
    monitors={"weather": MonitorWeather},
    devices=["influx_logger"],
    data_logger=my_db_logger,
)
