from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import StringParam
from ndscan.experiment.parameters import StringParamHandle


class TestParamHandleNamesFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_param(
            "testparam", StringParam, description="test param", default='"hello"'
        )
        self.testparam: StringParamHandle

    def run_once(self):
        print(self.testparam.name)
        print(self.testparam.get())


TestParamHandleNames = make_fragment_scan_exp(TestParamHandleNamesFrag)
