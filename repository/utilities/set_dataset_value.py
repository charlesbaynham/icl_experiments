"""Set a single float dataset from the schedule (for remote/headless use,
e.g. calibration thresholds and sabotage/demo values)."""

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import StringValue


class SetDatasetValue(EnvExperiment):
    def build(self):
        self.setattr_argument("name", StringValue(default="some.dataset"))
        self.setattr_argument("value", NumberValue(default=0.0, precision=6))

    def run(self):
        self.set_dataset(self.name, self.value, broadcast=True, persist=True)
        print(f"set {self.name} = {self.value}")
