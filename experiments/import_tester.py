
from artiq.experiment import EnvExperiment, NumberValue, kernel, delay, ms

from . import other

class ImportTester(EnvExperiment):
    def build(self):
        pass
 
    def run(self):
        print(other.hello())