from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLInOut
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.external_trigger import ExternalTriggerFrag


class TestExternalTriggerFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "trigger", ExternalTriggerFrag, ttl_name="ttl_50hz_trigger", auto_wait=False
        )
        self.trigger: ExternalTriggerFrag

    @kernel
    def run_once(self) -> None:
        print("Waiting for trigger...")
        self.core.break_realtime()

        self.trigger.wait_for_trigger()
        self.core.wait_until_mu(now_mu())
        print("Triggered!")


TestExternalTrigger = make_fragment_scan_exp(TestExternalTriggerFrag)


class TestExternalTriggerDirect(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("ttl1")
        self.ttl1: TTLInOut

    @kernel
    def run(self):
        self.core.break_realtime()

        self.ttl1.input()

        delay(1e-6)

        while True:
            self.core.break_realtime()
            fin = self.ttl1.gate_rising(1.0)
            # while True:
            r = self.ttl1.timestamp_mu(fin)
            print(r)

            # if r == -1:
            #     break
