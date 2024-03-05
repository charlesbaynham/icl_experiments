from typing import *

from artiq.experiment import *
from ndscan.experiment import *


class BaseThingDoer(Fragment):
    def build_fragment(self, thing_to_do: Callable):
        self.setattr_device("core")

        self.thing_to_do = thing_to_do

    @kernel
    def device_setup(self):
        self.thing_to_do(0.0)


class RedRampingPhaseWithFieldsAndSUServoBindings(BaseThingDoer):
    def build_fragment(self):
        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(thing_to_do=self.do_thing)

    @kernel
    def do_thing(self, val):
        print(val)


class NarrowRedCapturePhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    pass


class NarrowRedCompressionPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    pass


class RedPhaseUser(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.setattr_fragment(
            "frag1",
            NarrowRedCompressionPhase,
        )
        self.setattr_fragment(
            "frag2",
            NarrowRedCapturePhase,
        )

        self.frag1: NarrowRedCompressionPhase
        self.frag2: NarrowRedCapturePhase

    @kernel
    def run_once(self) -> None:
        self.frag1.do_phase()
        self.frag2.do_phase()


def test_failing_phase_compilation(fragment_precompiler):
    fragment_precompiler(RedPhaseUser)
