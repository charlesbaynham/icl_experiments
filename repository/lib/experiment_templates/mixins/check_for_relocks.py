from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.injected_diodes.relocker_board import RelockerChannelFrag
from artiq.language.core import kernel, rpc
from ndscan.experiment.result_channels import IntChannel

import logging

logger = logging.getLogger(__name__)


class CheckForRelocksMixin(RedMOTWithExperiment):
    """
    Mixin for checking if the red IJD relocker relocked during the experiment.
    """

    def build_fragment(self):

        self.setattr_fragment(
            "red_relocker",
            RelockerChannelFrag,
            channel_name="red_IJD1_relocker",
        )
        self.red_relocker: RelockerChannelFrag

        self.setattr_result("num_relocks", IntChannel)
        self.num_relocks: IntChannel
        super().build_fragment()

    @kernel
    def host_functions_after_experiment_hook(self):
        self.check_for_relocks_rpc()

    @rpc
    def check_for_relocks_rpc(self):
        num_relocks = self.red_relocker.get_auto_relock_stats()[0]
        if num_relocks:
            self.logger.warning(
                "Red IJD relocker relocked %d times during the experiment", num_relocks
            )
        self.num_relocks.push(num_relocks)
