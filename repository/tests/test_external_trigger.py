from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.external_trigger import ExternalTrigger


class TestExternalTriggerFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_fragment("trigger", ExternalTrigger, ttl_name="ttl_50hz_trigger")
        self.trigger: ExternalTrigger

    def run_once(self) -> None:
        print("Triggered!")


TestExternalTrigger = make_fragment_scan_exp(TestExternalTriggerFrag)
