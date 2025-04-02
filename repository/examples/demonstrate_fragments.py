from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from ndscan.experiment import FloatParam, FloatChannel
from ndscan.experiment.parameters import FloatParamHandle

class Demo1(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        self.setattr_param("num1", FloatParam, default=1.0, description="Number 1")
        self.num1 : FloatParamHandle

        self.setattr_param("num2", FloatParam, default=1.0, description="Number 2")
        self.num2 : FloatParamHandle

        self.setattr_result("sum", FloatChannel)
        self.sum: FloatChannel

    def run_once(self):
        the_sum = self.num1.get() + self.num2.get()
        print(f"Sum: {the_sum}")
class Demo2(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        pass

    def run_once(self):
        pass

class Demo3(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        pass

    def run_once(self):
        pass



Demo1Exp = make_fragment_scan_exp(Demo1)
Demo2Exp = make_fragment_scan_exp(Demo2)
Demo3Exp = make_fragment_scan_exp(Demo3)
