from artiq.experiment import EnvExperiment
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import create_and_run_fragment_once
from ndscan.experiment.entry_point import make_fragment_scan_exp


class HelloSayer(Fragment):
    def build_fragment(self) -> None:
        pass

    def say_hello(self):
        print("Hello world")


class MyExpFragment(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("hello_sayer", HelloSayer)
        self.hello_sayer: HelloSayer

        self.setattr_result("foo")
        self.foo: ResultChannel

    def run_once(self):
        self.hello_sayer.say_hello()

        self.foo.push(123)


class MyEnvExperiment(EnvExperiment):
    def run(self):
        results = create_and_run_fragment_once(self, MyExpFragment)
        print(results["foo"])


MyExpFragmentScan = make_fragment_scan_exp(MyExpFragment)
