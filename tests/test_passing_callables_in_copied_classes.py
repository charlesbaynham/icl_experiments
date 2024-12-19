from ndscan.experiment import ExpFragment
from ndscan.experiment import HasEnvironment
from ndscan.experiment import kernel


class SayerBase(HasEnvironment):
    def build(self, method):
        self.setattr_device("core")
        self.method = method

    @kernel
    def do(self):
        self.method()

    @kernel
    def say_hello(self):
        print("Hello")

    @kernel
    def say_world(self):
        print("world")


class HelloSayer(SayerBase):
    def build(self):
        return super().build(self.say_hello)


class WorldSayer(SayerBase):
    def build(self):
        return super().build(self.say_world)


class UserOfSubthings(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.subthing_a = HelloSayer(self)
        self.subthing_b = WorldSayer(self)

    @kernel
    def run_once(self) -> None:
        self.subthing_a.do()
        self.subthing_b.do()


def test_passing_callables(fragment_precompiler):
    fragment_precompiler(UserOfSubthings)
