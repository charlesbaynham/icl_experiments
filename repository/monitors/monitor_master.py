import logging

from artiq_influx_generic import InfluxController
from qbutler.monitoring import make_monitor_controller

from repository.database_monitors.monitor_heartbeat import MonitorHeartbeat
from repository.database_monitors.monitor_ijd_relockers import MonitorBlueIJDRelocker
from repository.database_monitors.monitor_ijd_relockers import MonitorRedIJDRelocker
from repository.database_monitors.monitor_ijds import MonitorBlueIJD1
from repository.database_monitors.monitor_ijds import MonitorBlueIJD2
from repository.database_monitors.monitor_ijds import MonitorBlueIJD3
from repository.database_monitors.monitor_ijds import MonitorRedIJD1
from repository.database_monitors.monitor_ion_pump import MonitorAIONCh1IonPump
from repository.database_monitors.monitor_ion_pump import MonitorAIONCh2IonPump
from repository.database_monitors.monitor_lab_temperature import (
    MonitorTemperatureDencoIn,
)
from repository.database_monitors.monitor_lab_temperature import (
    MonitorTemperatureDencoOut,
)
from repository.database_monitors.monitor_lab_temperature import MonitorTemperaturePCW
from repository.database_monitors.monitor_saes_ion_pump import MonitorClockCh1IonPump
from repository.database_monitors.monitor_saes_ion_pump import MonitorClockCh2IonPump
from repository.database_monitors.monitor_topticas import *
from repository.database_monitors.monitor_turbopump import MonitorTurbo
from repository.database_monitors.monitor_wand import MonitorWAND
from repository.database_monitors.monitor_weather import MonitorWeather

logger = logging.getLogger(__name__)


def my_db_logger(self, name, state, data_list):
    # Convert into a list of measurements if not already formatted like this
    if not isinstance(data_list, list):
        data_list = [data_list]

    for data in data_list:
        tags = {}

        # By setting "type" here, allow monitors to override it by passing their own "type" entry
        tags["type"] = name

        timestamp = None
        if isinstance(data, dict):
            if "fields" in data:
                fields = data["fields"]
                tags = tags | data["tags"]
                if "timestamp" in data:
                    timestamp = data["timestamp"]
            else:
                fields = data
        elif isinstance(data, float):
            fields = {"value": data}
        elif data is None:
            continue
        else:
            raise ValueError(
                f'Data "{data}" of type {type(data)} not supported - only floats and dicts are accepted'
            )

        logger.info(
            "Writing to database: type = %s, tags = %s, fields = %s", name, tags, fields
        )

        self.influx_logger: InfluxController
        self.influx_logger.write(tags=tags, fields=fields, timestamp=timestamp)


MonitorMaster = make_monitor_controller(
    "MonitorMaster",
    monitors={
        "weather": MonitorWeather,
        # "temperature_sidearm": MonitorTemperatureSidearm,  # TODO fix broken sidearm temperature sensor
        "temperature_denco_in": MonitorTemperatureDencoIn,
        "temperature_denco_out": MonitorTemperatureDencoOut,
        "temperature_PCW": MonitorTemperaturePCW,
        "ion_pump": MonitorAIONCh1IonPump,  # Keep legacy naming from when we only imagined one experiment
        "ion_pump_cham2": MonitorAIONCh2IonPump,
        "ion_pump_clock_ch1": MonitorClockCh1IonPump,
        "ion_pump_clock_ch2": MonitorClockCh2IonPump,
        "heartbeat": MonitorHeartbeat,
        "turbopump": MonitorTurbo,
        "blue_ijd1": MonitorBlueIJD1,
        "blue_ijd2": MonitorBlueIJD2,
        "blue_ijd3": MonitorBlueIJD3,
        "red_ijd1": MonitorRedIJD1,
        "wand": MonitorWAND,
        "toptica_461": MonitorToptica461,
        "toptica_487": MonitorToptica487,
        "toptica_641": MonitorToptica641,
        "toptica_679": MonitorToptica679,
        "toptica_689": MonitorToptica689,
        "toptica_698": MonitorToptica698,
        "toptica_707": MonitorToptica707,
        "toptica_1379": MonitorToptica1379,
        "blue_ijd_relocker": MonitorBlueIJDRelocker,
        "red_ijd_relocker": MonitorRedIJDRelocker,
    },
    devices=["influx_logger"],
    data_logger=my_db_logger,
)
MonitorMaster.__doc__ = "Start the database monitors"
