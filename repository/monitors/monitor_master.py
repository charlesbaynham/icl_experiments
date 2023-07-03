import logging

from artiq_influx_generic import InfluxController
from qbutler.monitoring import make_monitor_controller

from repository.monitors.monitor_covid import MonitorCOVID
from repository.monitors.monitor_heartbeat import MonitorHeartbeat
from repository.monitors.monitor_ijds import MonitorBlueIJD1
from repository.monitors.monitor_ijds import MonitorBlueIJD2
from repository.monitors.monitor_ijds import MonitorBlueIJD3
from repository.monitors.monitor_ijds import MonitorRedIJD1
from repository.monitors.monitor_ion_pump import MonitorIonPump
from repository.monitors.monitor_ionpump_duplicate import MonitorIonPumpDup
from repository.monitors.monitor_lab_temperature import MonitorLabTemperature
from repository.monitors.monitor_turbopump import MonitorTurbo
from repository.monitors.monitor_weather import MonitorWeather

logger = logging.getLogger(__name__)


def my_db_logger(self, name, state, data):
    tags = {}
    timestamp = None
    if isinstance(data, dict):
        if "fields" in data:
            fields = data["fields"]
            tags = data["tags"]
            if "timestamp" in data:
                timestamp = data["timestamp"]
            assert "type" not in tags
        else:
            fields = data
    elif isinstance(data, float):
        fields = {"value": data}
    elif data is None:
        return
    else:
        raise ValueError(
            "Data type %s not supported - only floats and dicts are accepted", data
        )

    tags["type"] = name

    logger.info(
        "Writing to database: type = %s, tags = %s, fields = %s", name, tags, fields
    )

    self.influx_logger: InfluxController
    self.influx_logger.write(tags=tags, fields=fields, timestamp=timestamp)


MonitorMaster = make_monitor_controller(
    "MonitorMaster",
    monitors={
        "weather": MonitorWeather,
        "temperature": MonitorLabTemperature,
        "ion_pump": MonitorIonPump,
        "ion_pump_cham2": MonitorIonPumpDup,
        "covid": MonitorCOVID,
        "heartbeat": MonitorHeartbeat,
        "turbopump": MonitorTurbo,
        "blue_ijd1": MonitorBlueIJD1,
        "blue_ijd2": MonitorBlueIJD2,
        "blue_ijd3": MonitorBlueIJD3,
        "red_ijd1": MonitorRedIJD1,
    },
    devices=["influx_logger"],
    data_logger=my_db_logger,
)
