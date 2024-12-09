from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.injected_diodes.relocker_board import RelockerChannelFrag
from artiq.language.core import kernel, rpc
from ndscan.experiment.result_channels import IntChannel
from repository.lib.constants import IJD_RELOCKER_DEFAULTS
from typing import List

import logging

logger = logging.getLogger(__name__)


class CheckForRelocksMixin(RedMOTWithExperiment):
    """
    Mixin for checking if the IJD relockers relocked during the experiment.
    """

    def build_fragment(self):

        self.relockers: List[RelockerChannelFrag] = []
        self.num_relock_channels: List[IntChannel] = []

        for channel_name in IJD_RELOCKER_DEFAULTS.keys():
            relocker = self.setattr_fragment(
                channel_name,
                RelockerChannelFrag,
                channel_name=channel_name,
            )
            self.relockers.append(relocker)

            result_channel = self.setattr_result(
                f"{channel_name}_num_relocks",
                IntChannel,
                display_hints={"priority": -1},
            )
            self.num_relock_channels.append(result_channel)

        # self.setattr_fragment(
        #     "red_relocker",
        #     RelockerChannelFrag,
        #     channel_name="red_IJD1_relocker",
        # )
        # self.red_relocker: RelockerChannelFrag

        # self.setattr_result("num_relocks", IntChannel, display_hints={"priority": -1})
        # self.num_relocks: IntChannel
        super().build_fragment()

    def host_setup(self):
        super().host_setup()
        # reset the relocker stats at the start of the scan
        for relocker in self.relockers:
            relocker.get_auto_relock_stats()
        self.post_experiment_functions.append(self.check_for_relocks_rpc)

    # @kernel
    # def host_functions_after_experiment_hook(self):
    #     self.check_for_relocks_rpc()

    @rpc
    def check_for_relocks_rpc(self):
        for i, relocker in enumerate(self.relockers):
            num_relocks = relocker.get_auto_relock_stats()[0]
            if num_relocks:
                logger.warning(
                    "%s relocker relocked %d times during the experiment",
                    relocker.channel_name,
                    num_relocks,
                )
            self.num_relock_channels[i].push(num_relocks)

        # num_relocks = self.red_relocker.get_auto_relock_stats()[0]
        # if num_relocks:
        #     logger.warning(
        #         "Red IJD relocker relocked %d times during the experiment", num_relocks
        #     )
        # self.num_relocks.push(num_relocks)
