from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.injected_diodes.relocker_board import RelockerChannelFrag
from artiq.language.core import kernel, rpc
from ndscan.experiment.result_channels import IntChannel
from repository.lib.constants import IJD_RELOCKER_DEFAULTS
from relocker_driver.driver import RelockerDriver
from typing import List

import logging

logger = logging.getLogger(__name__)


class CheckForRelocksMixin(RedMOTWithExperiment):
    """
    Mixin for checking if the IJD relockers relocked during the experiment.
    """

    def build_fragment(self):

        self.relockers: List[RelockerDriver] = []
        self.num_relock_channels: List[IntChannel] = []
        self.channel_names = IJD_RELOCKER_DEFAULTS.keys()

        for channel_name in self.channel_names:
            defaults = IJD_RELOCKER_DEFAULTS[channel_name]
            board_name = defaults["board_name"]
            relocker: RelockerDriver = self.get_device(board_name)
            self.relockers.append(relocker)

            result_channel = self.setattr_result(
                f"{channel_name}_num_relocks",
                IntChannel,
                display_hints={"priority": -1},
            )
            self.num_relock_channels.append(result_channel)

        super().build_fragment()

    def host_setup(self):
        super().host_setup()
        # reset the relocker stats at the start of the scan
        for relocker in self.relockers:
            relocker.get_auto_relock_stats()

    @kernel
    def host_functions_after_experiment_hook(self):
        self.check_for_relocks_rpc()

    @rpc(flags={"async"})
    def check_for_relocks_rpc(self):
        for i, channel_name in enumerate(self.channel_names):
            channel = IJD_RELOCKER_DEFAULTS[channel_name]["channel"]
            relocker = self.relockers[i]
            num_relocks = relocker.get_auto_relock_stats(channel)[0]
            if num_relocks:
                logger.warning(
                    "%s relocker relocked %d times during the experiment",
                    channel_name,
                    num_relocks,
                )
            self.num_relock_channels[i].push(num_relocks)
