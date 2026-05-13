from artiq.coredevice.core import Core
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.external_trigger import ExternalTrigger


class TestExternalTriggerFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "trigger", ExternalTrigger, ttl_name="ttl_50hz_trigger", auto_wait=False
        )
        self.trigger: ExternalTrigger

    @kernel
    def run_once(self) -> None:
        print("Waiting for trigger...")
        self.core.break_realtime()

        self.trigger.wait_for_trigger()
        self.core.wait_until_mu(now_mu())
        print("Triggered!")


TestExternalTrigger = make_fragment_scan_exp(TestExternalTriggerFrag)
