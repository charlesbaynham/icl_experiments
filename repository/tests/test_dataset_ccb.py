import time

import numpy as np
from artiq.experiment import EnvExperiment


class TestCCBPlotting(EnvExperiment):
    """Test CCB Plotting"""

    def build(self):
        self.setattr_device("ccb")

    def run(self):
        cmd = f"${{artiq_applet}}plot_xy parabola_y --x parabola_x"
        self.ccb.issue("create_applet", "Test plot", cmd)

        x_vals = np.linspace(0, 1, 10)

        self.set_dataset("parabola_x", x_vals, broadcast=True)
        self.set_dataset("parabola_y", np.full(10, np.nan), broadcast=True)

        for i in range(10):
            self.mutate_dataset("parabola_y", i, x_vals[i] ** 2)
            time.sleep(0.5)
