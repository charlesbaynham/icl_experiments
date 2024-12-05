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

    def host_setup(self):
        super().host_setup()
        self.setattr_result("frequency", FloatChannel, display_hints={"priority": -1})
        self.frequency: FloatChannel

    @kernel
    def check_counter_hook(self):
        self.check_counter_rpc()

    @rpc
    def check_counter_rpc(self):
        frequency = self.rigol.get_frequency()
        if abs(frequency - CLOCK_LASER_BEATNOTE_FREQUENCY) > 30e-3:
            logger.warning(
                "Frequency %.2f is too far from expected %.2f",
                frequency,
                CLOCK_LASER_BEATNOTE_FREQUENCY,
            )

        self.frequency.push(frequency)
