import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp


logger = logging.getLogger(__name__)


class TestBuild(ExpFragment):
    def build_fragment(self):
        self.setattr_param("testparam", FloatParam, description="A test", default=123.0)

        try:
            print(self.testparam.get())
        except AttributeError:
            print("There was an error")

    def run_once(self) -> None:
        print("run_once")
        print(self.testparam.get())


TestBuildExp = make_fragment_scan_exp(TestBuild)
