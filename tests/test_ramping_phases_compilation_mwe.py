from typing import *

from artiq.experiment import *
from ndscan.experiment import *


class ThingDoerBase(Fragment):
    def build_fragment(self, thing_to_do: Callable):
        self.setattr_device("core")

        self.thing_to_do = thing_to_do

    @kernel
    def device_setup(self):
        self.thing_to_do(0.0)


class ThingDoerMid(ThingDoerBase):
    def build_fragment(self):
        # Build a ThingDoerBase does a specific thing
        return super().build_fragment(thing_to_do=self.do_thing)

    @kernel
    def do_thing(self, val):
        print(val)


# Define classes that reimplement ThingDoerMid (e.g. because you want to
# customise some class parameters etc, not shown here)
class ThingDoerConcreteA(ThingDoerMid):
    pass


class ThingDoerConcreteB(ThingDoerMid):
    pass


class RedPhaseUser(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.setattr_fragment(
            "frag1",
            ThingDoerConcreteB,
        )
        self.setattr_fragment(
            "frag2",
            ThingDoerConcreteA,
        )

        self.frag1: ThingDoerConcreteB
        self.frag2: ThingDoerConcreteA

    @kernel
    def run_once(self) -> None:
        self.frag1.do_phase()
        self.frag2.do_phase()


def test_failing_phase_compilation(fragment_precompiler):
    fragment_precompiler(RedPhaseUser)
