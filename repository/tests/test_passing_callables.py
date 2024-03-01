from artiq.experiment import *
from ndscan.experiment import *


class SubthingDooer(HasEnvironment):
    def build(self, arg="hello"):
        self.setattr_device("core")
        self.arg = arg

    @kernel
    def do(self):
        print(self.arg)


class DifferentDooer(HasEnvironment):
    def build(self, other_arg="hello"):
        self.setattr_device("core")
        self.other_arg = other_arg

    @kernel
    def do_the_thing(self):
        print(self.other_arg)


class UserOfSubthing(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")

        self.subthing_a = SubthingDooer(self, arg="hello")
        self.subthing_b = SubthingDooer(self, arg="world")
        self.subthing_c = DifferentDooer(self, other_arg="!")

        self.methods = [
            self.subthing_a.do,
            self.subthing_b.do,
            self.subthing_c.do_the_thing,
        ]

    @kernel
    def run_once(self) -> None:
        for i in range(len(self.methods)):
            self.methods[i]()


TestPassingCallables = make_fragment_scan_exp(UserOfSubthing)
