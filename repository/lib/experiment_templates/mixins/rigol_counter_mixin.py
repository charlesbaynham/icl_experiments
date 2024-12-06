from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.rigol_counter import RigolCounterFrag
from repository.lib.constants import CLOCK_LASER_BEATNOTE_FREQUENCY

from ndscan.experiment.result_channels import FloatChannel

from artiq.language import rpc
from artiq.language import kernel

import logging

logger = logging.getLogger(__name__)


class RigolCounterMixin(RedMOTWithExperiment):

    def build_fragment(self):
        self.setattr_fragment(
            "rigol",
            RigolCounterFrag,
        )
        self.rigol: RigolCounterFrag
        self.setattr_result(
            "rigol_counter_frequency", FloatChannel, display_hints={"priority": -1}
        )
        self.rigol_counter_frequency: FloatChannel
        super().build_fragment()

    def host_setup(self):
        super().host_setup()

    @kernel
    def check_counter_hook(self):
        self.check_counter_rpc()

    @rpc
    def check_counter_rpc(self):
        frequency = self.rigol.get_frequency()
        if abs(frequency - CLOCK_LASER_BEATNOTE_FREQUENCY) > 200e-3:
            logger.warning(
                "Frequency %.2f is too far from expected %.2f",
                frequency,
                CLOCK_LASER_BEATNOTE_FREQUENCY,
            )

        self.rigol_counter_frequency.push(CLOCK_LASER_BEATNOTE_FREQUENCY - frequency)
