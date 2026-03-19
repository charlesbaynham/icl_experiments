import logging
from typing import List

import numpy as np
from artiq.language.core import host_only
from artiq.language.core import rpc
from ndscan.experiment.fragment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.result_channels import IntChannel
from relocker_driver.driver import RelockerDriver

from repository.lib.constants import IJD_RELOCKER_DEFAULTS

logger = logging.getLogger(__name__)


class CheckForRelocksFrag(Fragment):
    """
    This fragment checks for relocks on the IJD relockers after the experiment.
    """

    def build_fragment(self, reset_at_start: bool = True):
        self.reset_at_start = reset_at_start

        self.setattr_param(
            "enabled",
            BoolParam,
            "Enable relock checks",
            default=True,
        )
        self.enabled: BoolParamHandle

        self.relockers: List[RelockerDriver] = []
        self.num_relock_channels: List[IntChannel] = []
        self.channel_names = list(IJD_RELOCKER_DEFAULTS.keys())

        self.total_relocks = self.setattr_result(
            "total_num_relocks",
            IntChannel,
            display_hints={"priority": -1},
        )
        self.total_relocks: IntChannel

        for channel_name in self.channel_names:
            defaults = IJD_RELOCKER_DEFAULTS[channel_name]
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
        if self.enabled.get() and self.reset_at_start:
            self.check_for_relocks()

    @host_only
    def check_for_relocks(self):
        n_relocks = []
        for i, channel_name in enumerate(self.channel_names):
            defaults = IJD_RELOCKER_DEFAULTS[channel_name]
            channel = defaults.channel
            relocker = self.relockers[i]
            try:
                result = relocker.get_auto_relock_stats(channel)

            # Work around bug in IJD comms for now, but this should be fixed elsewhere
            except Exception:
                result = None

            if result is None:
                # Connection error
                logger.error("Could not get relock stats for %s", channel_name)
                n_relocks.append(1)
            else:
                n_relocks.append(result[0])

        return n_relocks

    @rpc
    def check_and_log_relocks(self) -> np.int32:
        if not self.enabled.get():
            for channel in self.num_relock_channels:
                channel.push(0)
            self.total_relocks.push(0)
            return 0

        relocks_total = 0
        num_relolocks = self.check_for_relocks()
        for i, n in enumerate(num_relolocks):
            if n:
                logger.info(
                    "%s relocker relocked %d times during the experiment",
                    self.channel_names[i],
                    n,
                )
            self.num_relock_channels[i].push(n)
            relocks_total += n
        self.total_relocks.push(relocks_total)
        if relocks_total > 0:
            logger.warning(
                "Total number of ijd relocks during the experiment: %d", relocks_total
            )
        return int(sum(num_relolocks))
