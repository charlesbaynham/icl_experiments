import logging
from datetime import datetime

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from uk_covid19 import Cov19API

logger = logging.getLogger(__name__)


LONDON_ONLY_FILTER = ["areaType=region", "areaName=London"]

NEW_CASES_STRUCTURE = {
    "date": "date",
    "newCasesByPublishDate": "newCasesByPublishDate",
}

DELAY = 12 * 3600  # Query every 12 hours


class MonitorCOVID(Calibration):
    def build_calibration(self):
        self.set_timeout(DELAY)
        self.latest_datetime = None

    def run_once(self):
        new_datetime, new_cases = self.get_data()

        if new_datetime != self.latest_datetime:
            self.latest_datetime = new_datetime

            self.status.push(CalibrationResult.OK)
            self.data.push({"fields": {"new_cases": new_cases}, "tags": {}})

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
