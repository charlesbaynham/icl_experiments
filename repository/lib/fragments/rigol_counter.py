import logging

from artiq.language import host_only
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import Fragment

from repository.lib.constants import CLOCK_LASER_BEATNOTE_FREQUENCY
from repository.lib.fragments.rigol.rigol_device import RigolCounter

logger = logging.getLogger(__name__)


class RigolCounterFrag(Fragment):
    def build_fragment(self):
        self.rigol_counter: RigolCounter = self.get_device("rigol_counter")
        self.rigol_counter_frequency = self.setattr_result(
            "rigol_counter_frequency",
            FloatChannel,
            display_hints={"priority": -1},
        )

    @host_only
    def host_setup(self):
        self.rigol_counter.setup_measurement()
        super().host_setup()

    @rpc
    def check_counter_rpc(self):
        frequency = self.rigol_counter.get_frequency()
        if abs(frequency - CLOCK_LASER_BEATNOTE_FREQUENCY) > 200e-3:
            logger.warning(
                "Frequency %.2f is too far from expected %.2f",
                frequency,
                CLOCK_LASER_BEATNOTE_FREQUENCY,
            )

        self.rigol_counter_frequency.push(frequency)
