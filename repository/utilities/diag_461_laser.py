"""Read-only 461 Toptica diagnostics: piezo, current, external input state.

For diagnosing a runaway/railed 461 without touching anything.
"""

import logging

from artiq.experiment import EnvExperiment
from toptica_wrapper.driver import TopticaDLCPro

logger = logging.getLogger(__name__)


class Diag461Laser(EnvExperiment):
    def build(self):
        self.toptica_461: TopticaDLCPro = self.get_device("toptica_461")

    def run(self):
        dlcpro = self.toptica_461.get_dlcpro()
        dlcpro.open()
        laser = self.toptica_461.get_laser()

        pc = laser.dl.pc
        for name, node in [
            ("pc.voltage_set", pc.voltage_set),
            ("pc.voltage_act", pc.voltage_act),
            ("pc.voltage_min", pc.voltage_min),
            ("pc.voltage_max", pc.voltage_max),
            ("pc.enabled", pc.enabled),
            ("pc.external_input.enabled", pc.external_input.enabled),
            ("pc.external_input.signal", pc.external_input.signal),
            ("pc.external_input.factor", pc.external_input.factor),
            ("cc.current_set", laser.dl.cc.current_set),
            ("cc.current_act", laser.dl.cc.current_act),
            ("cc.enabled", laser.dl.cc.enabled),
        ]:
            try:
                print(f"461 {name} = {node.get()}")
            except Exception as e:
                print(f"461 {name} read failed: {e!r}")
