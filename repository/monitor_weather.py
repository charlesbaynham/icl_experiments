import json
import logging
import time
from pprint import pformat

import requests
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.language.core import TerminationRequested
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController

logger = logging.getLogger(__name__)

# API call details for weatherbit.io

# Note that this is a paid-for service, linked to Charles' personal account
# We're on the free tier and only get 500 calls per day. If you are reading this
# as an external user, please don't use this key! You'll stop our monitor from
# working and force me to think about key security :(
QUERY_URL = "https://api.weatherbit.io/v2.0/current"
API_KEY = "3096e39b1e984ee996eb2ffd3a8d2579"
QUERY_STR = {
    "lon": "-0.17901159470066544",
    "lat": "51.499391511681495",
    "units": "metric",
    "lang": "en",
    "key": API_KEY,
}


class MonitorWeather(EnvExperiment):
    """
    MonitorWeather

    Query the temperature of a weather sensor near the Blackett lab
    """

    def build(self):
        self.setattr_argument(
            "delay", NumberValue(default=300, scale=1, step=1, ndecimals=0, min=300)
        )

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.set_default_scheduling(pipeline_name=f"weather")

    @staticmethod
    def get_weather():
        response = requests.request("GET", QUERY_URL, params=QUERY_STR)

        if not response.ok:
            raise RuntimeError(
                f"API query failed with error code {response.status_code}"
            )

        parsed = json.loads(response.text)
        data = parsed["data"][0]

        logger.debug("Full weather report:")
        logger.debug(pformat(data))

        measurement_timestamp = data["ts"]

        return measurement_timestamp, {
            "solar_rad": data["solar_rad"],
            "temperature": data["temp"],
            "pressure": data["pres"],
            "relative_humidity": data["rh"],
        }

    def run(self):
        last_timestamp = None

        while True:
            try:
                timestamp, weather_data = self.get_weather()

                print(weather_data)

                if timestamp != last_timestamp:
                    last_timestamp = timestamp
                    self.influx_logger.write(
                        tags={"type": "weather"},
                        fields=weather_data,
                        timestamp=timestamp,
                    )

                self.scheduler.pause()
                time.sleep(self.delay)

            except Exception as e:
                if isinstance(e, (KeyboardInterrupt, TerminationRequested)):
                    break
                else:
                    logger.error("Error occured:", exc_info=e)
                    if self.scheduler.check_pause():
                        return
