from artiq.experiment import *
from ndscan.experiment import *


class SubthingDooer(HasEnvironment):
    def build(self, arg="hello"):
        self.setattr_device("core")
        self.arg = arg

    @kernel
    def do(self):
        print(self.arg)


class UserOfSubthing(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")

        self.subthing_a = SubthingDooer(self, arg="hello")
        self.subthing_b = SubthingDooer(self, arg="world")

        self.methods = [self.subthing_a.do, self.subthing_b.do]

    @kernel
    def run_once(self) -> None:
        for i in range(len(self.methods)):
            self.methods[i]()
