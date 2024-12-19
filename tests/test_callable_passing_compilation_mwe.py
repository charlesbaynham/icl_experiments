import pytest
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import kernel


class ThingDoerBase(Fragment):
    def build_fragment(self):
        self.setattr_device("core")

        self.thing_to_do = self.do_thing

    @kernel
    def device_setup(self):
        self.thing_to_do(0.0)

    @kernel
    def do_thing(self, val):
        print(val)


class ThingDoerConcreteA(ThingDoerBase):
    pass


class ThingDoerConcreteB(ThingDoerBase):
    pass


class ThingDoerExperiment(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.setattr_fragment(
            "frag1",
            ThingDoerConcreteA,
        )
        self.setattr_fragment(
            "frag2",
            ThingDoerConcreteB,
        )

    @kernel
    def run_once(self) -> None:
        pass


@pytest.mark.xfail
def test_failing_phase_compilation(fragment_precompiler):
    fragment_precompiler(ThingDoerExperiment)
