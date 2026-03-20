import logging
from typing import List

from artiq.language.core import host_only
from artiq.language.core import kernel
from artiq.language.core import rpc
from ndscan.experiment.result_channels import IntChannel
from relocker_driver.driver import RelockerDriver

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

logger = logging.getLogger(__name__)


class CheckForRelocksFrag(RedMOTCheckpoints):
    """
    This fragment checks for relocks on the IJD relockers after the experiment.
    """

    def build_fragment(self, reset_at_start: bool = True):
        self.reset_at_start = reset_at_start

        self.relockers: List[RelockerDriver] = []
        self.num_relock_channels: List[IntChannel] = []
        self.channel_names = list(constants.IJD_RELOCKER_DEFAULTS.keys())

        for channel_name in self.channel_names:
            defaults = constants.IJD_RELOCKER_DEFAULTS[channel_name]
            board_name = defaults.board_name
            relocker: RelockerDriver = self.get_device(board_name)
            self.relockers.append(relocker)

            result_channel = self.setattr_result(
                f"{channel_name}_num_relocks",
                IntChannel,
                display_hints={"priority": -1},
            )
            self.num_relock_channels.append(result_channel)

    def host_setup(self):
        super().host_setup()
        # reset the relocker stats at the start of the scan
        if self.reset_at_start:
            self.check_for_relocks()

    @host_only
    def check_for_relocks(self):
        n_relocks = []
        for i, channel_name in enumerate(self.channel_names):
            defaults = constants.IJD_RELOCKER_DEFAULTS[channel_name]
            channel = defaults.channel
            relocker = self.relockers[i]
            n_relocks.append(relocker.get_auto_relock_stats(channel)[0])
        return n_relocks

    @rpc(flags={"async"})
    def check_and_log_relocks(self):
        num_relolocks = self.check_for_relocks()
        for i, n in enumerate(num_relolocks):
            if n:
                logger.warning(
                    "%s relocker relocked %d times during the experiment",
                    self.channel_names[i],
                    n,
                )
            self.num_relock_channels[i].push(n)

    @kernel
    def after_data_saved_checkpoint(self):
        self.after_data_saved_checkpoint_subfragments()

        self.check_and_log_relocks()


class CheckForRelocksMixin(RedMOTWithExperiment):
    """
    Mixin for checking if the IJD relockers relocked during the experiment.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("relock_checker", CheckForRelocksFrag)
