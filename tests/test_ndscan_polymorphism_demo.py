import pytest
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment


class TopLevelFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

        self.setattr_fragment("subfrag_1", MidLevelFrag, ["hello", "world"])
        self.setattr_fragment(
            "subfrag_2", MidLevelFrag, ["different", "strings", "here"]
        )

    @kernel
    def run_once(self) -> None:
        self.subfrag_1.do_many_somethings()
        self.subfrag_2.do_many_somethings()


class MidLevelFrag(Fragment):
    def build_fragment(self, list_of_strings):
        self.setattr_device("core")

        self.subfrags = []
        for my_string in list_of_strings:
            self.subfrags.append(
                self.setattr_fragment(
                    "subfrag_" + my_string, BottomLevelFrag, bottom_frag_arg=my_string
                )
            )

    @kernel
    def do_many_somethings(self):
        for frag in self.subfrags:
            frag.do_something()

    @kernel
    def device_setup(self) -> None:
        print("setup here")
        self.device_setup_subfragments()


class BottomLevelFrag(Fragment):
    def build_fragment(self, bottom_frag_arg=None):
        self.setattr_device("core")

        self.arg = bottom_frag_arg

    @kernel
    def do_something(self):
        print(self.arg)

    @kernel
    def device_setup(self) -> None:
        print("setup here")
        self.device_setup_subfragments()


@pytest.mark.xfail(reason="Expected behaviour, but watch out for it")
def test_ndscan_polymorphism_bug(fragment_precompiler):
    fragment_precompiler(TopLevelFrag)
