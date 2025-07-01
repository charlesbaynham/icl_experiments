import time

from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import Fragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle


class NumberAdder(Fragment):
    def build_fragment(self, *args, **kwargs):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param("num1", FloatParam, default=1.0, description="Number 1")
        self.num1: FloatParamHandle

        self.setattr_param("num2", FloatParam, default=1.0, description="Number 2")
        self.num2: FloatParamHandle

        self.setattr_result("sum", FloatChannel)
        self.sum: FloatChannel

        self.some_other_number = 0.0

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.some_other_number = 10.0

    @kernel
    def add_numbers(self):
        the_sum = self.num1.get() + self.num2.get() + self.some_other_number

        time.sleep(0.1)

        self.sum.push(the_sum)


class Demo1(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        self.setattr_fragment("adder", NumberAdder)
        self.adder: NumberAdder

        self.setattr_fragment("adder2", NumberAdder)
        self.adder2: NumberAdder

    @kernel
    def run_once(self):
        self.adder.add_numbers()
        self.adder2.add_numbers()


class Demo3(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        pass

    def run_once(self):
        pass


Demo1Exp = make_fragment_scan_exp(Demo1)

Demo3Exp = make_fragment_scan_exp(Demo3)
