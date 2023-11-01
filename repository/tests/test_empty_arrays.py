# https://github.com/m-labs/artiq/issues/1626

from ndscan.experiment import ExpFragment
from artiq.experiment import kernel
import numpy as np


class Bug(ExpFragment):
    """Bug"""

    def build_fragment(self):
        self.core = self.get_device("core")
        # self.points = np.array([], dtype=np.float64)
        self.points = []

    @kernel
    def run_once(self):
        scans = self.points  # bug is here
        for pi in scans:
            self.do_measure(pi)  # it is necessary to call this function both here
        self.do_measure(0.0)  # and here to reproduce this bug

    @kernel
    def do_measure(self, point):
        result = 0
