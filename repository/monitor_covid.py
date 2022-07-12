import json
import logging
import time
from datetime import datetime
from pprint import pformat

import requests
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.language.core import TerminationRequested
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from uk_covid19 import Cov19API

logger = logging.getLogger(__name__)


LONDON_ONLY_FILTER = ["areaType=region", "areaName=London"]

NEW_CASES_STRUCTURE = {
    "date": "date",
    "newCasesByPublishDate": "newCasesByPublishDate",
}

DELAY = 12 * 3600  # Query every 12 hours


class MonitorCOVID(EnvExperiment):
    def build(self):
        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.set_default_scheduling(pipeline_name=f"covid")

        self.latest_datetime = None

    def run(self):
        while True:
            try:
                new_datetime, new_cases = self.get_data()

                if new_datetime != self.latest_datetime:
                    self.latest_datetime = new_datetime

                    self.influx_logger.write(
                        tags={"type": "covid"},
                        fields={"new_cases": new_cases},
                        timestamp=new_datetime.timestamp(),
                    )

                self.scheduler.pause()
                time.sleep(DELAY)

            except Exception as e:
                if isinstance(e, (KeyboardInterrupt, TerminationRequested)):
                    break
                else:
                    logger.error("Error occured:", exc_info=e)
                    if self.scheduler.check_pause():
                        return

    @staticmethod
    def get_data():
        api = Cov19API(
            filters=LONDON_ONLY_FILTER,
            structure=NEW_CASES_STRUCTURE,
            latest_by="newCasesByPublishDate",
        )
        data = api.get_json()["data"]

        assert len(data) == 1

        dates = datetime.strptime(data[0]["date"], "%Y-%m-%d")
        cases = data[0]["newCasesByPublishDate"]

        return dates, cases
