from ndscan.experiment import ExpFragment, make_fragment_scan_exp


class Demo1(ExpFragment):
    def build_fragment(self, *args, **kwargs):
        pass

    def run_once(self):
        pass

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