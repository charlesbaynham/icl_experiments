import logging

from artiq_influx_generic import InfluxController
from monitor_lab_temperature import MonitorLabTemperature
from monitor_weather import MonitorWeather
from qbutler.monitoring import make_monitor_controller

logger = logging.getLogger(__name__)


def my_db_logger(self, name, state, data):

    tags = {}
    if isinstance(data, dict):
        if "fields" in data:
            fields = data["fields"]
            tags = data["tags"]
            assert "type" not in tags
        else:
            fields = data
    elif isinstance(data, float):
        fields = {"value": data}
    else:
        raise ValueError(
            "Data type %s not supported - only floats and dicts are accepted", data
        )

    tags["type"] = name

    logger.debug(
        "Writing to database: type = %s, tags = %s, fields = %s", name, tags, data
    )

    self.influx_logger: InfluxController
    self.influx_logger.write(
        tags=tags,
        fields=fields,
    )


MyMonitorMaster = make_monitor_controller(
    "MyMonitorMaster",
    monitors={"weather": MonitorWeather, "temperature": MonitorLabTemperature},
    devices=["influx_logger"],
    data_logger=my_db_logger,
)
