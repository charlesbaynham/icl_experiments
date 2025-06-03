import logging

from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.timestamp_synchronizer import Timestamper

logger = logging.getLogger(__name__)


class TestTimestamperFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("timestamper", Timestamper, automatic_timestamp=True)

    @kernel
    def run_once(self):
        print("Done!")


class TestTimestamperManualFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("timestamper", Timestamper, automatic_timestamp=False)
        self.timestamper: Timestamper

        self.slack_consumption = self.setattr_result(
            "slack_consumption", FloatChannel, unit="s", min=0
        )

    @kernel
    def run_once(self):
        self.core.break_realtime()
        t_start_mu = self.core.get_rtio_counter_mu()
        self.timestamper.mark_timestamp()
        t_end_mu = self.core.get_rtio_counter_mu()

        slack_consumption = self.core.mu_to_seconds(t_end_mu - t_start_mu)
        self.slack_consumption.push(slack_consumption)

        logger.info(
            "Consumed %.1f us of slack",
            1e6 * slack_consumption,
        )


class TestTimestamperManualBrokenFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("timestamper", Timestamper, automatic_timestamp=False)

    @kernel
    def run_once(self):
        print("This should throw an error")


TestTimestamper = make_fragment_scan_exp(TestTimestamperFrag)
TestTimestamperManual = make_fragment_scan_exp(TestTimestamperManualFrag)
TestTimestamperManualBroken = make_fragment_scan_exp(TestTimestamperManualBrokenFrag)
