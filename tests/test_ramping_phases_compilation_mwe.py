from typing import *

from artiq.experiment import *
from ndscan.experiment import *


class GeneralRampingPhase(Fragment):
    def build_fragment(self, *args, general_setter: Optional[Callable] = None):
        self.setattr_device("core")

        self.general_setter = general_setter or self._do_nothing

    @kernel
    def _do_nothing(self, val):
        pass

    @kernel
    def device_setup(self):
        self.general_setter(0.0)

    @kernel
    def do_phase(self):
        pass


class RedRampingPhaseWithFieldsAndSUServoBindings(GeneralRampingPhase):
    def build_fragment(self):
        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(general_setter=self.do_thing)

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
