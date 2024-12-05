from repository.lib.fragments.rigol_counter import RigolCounterFrag, GATE_TIMES

from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.entry_point import make_fragment_scan_exp
from artiq.experiment import EnumerationValue
import logging
from time import sleep

logger = logging.getLogger(__name__)


class TestRigolCounterFrag(ExpFragment):
    def build_fragment(self):

        self.setattr_fragment("rigol", RigolCounterFrag)
        self.rigol: RigolCounterFrag

        self.setattr_argument(
            "gate_time",
            EnumerationValue(list(GATE_TIMES.keys()), default="10 s"),
            "Gate time",
        )
        self.gate_time: str

        self.setattr_param("wait_time", FloatParam, "Wait time", default=1.0, unit="s")
        self.wait_time: FloatParamHandle

        self.setattr_param(
            "n_measurements", IntParam, "Number of measurements", default=10
        )
        self.n_measurements: IntParamHandle

    def host_setup(self):
        self.rigol.gate_time_index = self.gate_time
        super().host_setup()

    def run_once(self):
        for _ in range(self.n_measurements.get()):
            frequency = self.rigol.get_frequency()
            logger.info("Frequency: %.2f", frequency)
            frequency_str = self.rigol.get_frequency_str()
            logger.info("Frequency string: %s", frequency_str)
            sleep(self.wait_time.get())


TestRigolCounter = make_fragment_scan_exp(TestRigolCounterFrag)
