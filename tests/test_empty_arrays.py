import numpy as np
import pytest
from artiq.experiment import TFloat
from artiq.experiment import TList
from artiq.language import kernel
from ndscan.experiment import ExpFragment


class EmptyFloatArray(ExpFragment):
    """
    Try to loop over an empty array. This fails because ARTIQ cannot tell the
    type, despite it being specified by numpy

    See https://github.com/m-labs/artiq/issues/1626
    """

    def build_fragment(self):
        self.core = self.get_device("core")
        self.points = np.array([], dtype=np.float64)

    @kernel
    def run_once(self):
        scans = self.points
        for p in scans:
            self.do_measure(p)

    @kernel
    def do_measure(self, point):
        point + 1


@pytest.mark.xfail(reason="ARTIQ issue #1626")
def test_empty_float_array(fragment_precompiler):
    fragment_precompiler(EmptyFloatArray)


class EmptyFloatArrayWithHints(ExpFragment):
    """
    Solve the problem with a hack: use the unknown list as the parameter to a
    function with explicit type annotations so the compiler can figure it out
    """

    def build_fragment(self):
        self.core = self.get_device("core")
        self.points = []

    @kernel
    def run_once(self):
        self.do_loop(self.points)

    @kernel
    def do_loop(self, list_of_points: TList(TFloat)):
        for p in list_of_points:
            self.do_measure(p)

    @kernel
    def do_measure(self, point):
        point + 1


def test_empty_float_array_with_hints(fragment_precompiler):
    fragment_precompiler(EmptyFloatArrayWithHints)


class EmptyTTLArrayWithDummy(ExpFragment):
    """
    Sadly, the hack above doesn't work: I can't type annotate arbitary objects. :(

    So I have to use this even-uglier hack.
    """

    def build_fragment(self):
        self.core = self.get_device("core")
        self.ttls = [self.get_device("ttl0")]

    @kernel
    def run_once(self):
        self.ttls = self.ttls[1:]

        for ttl in self.ttls:
            ttl.set_o(True)


def test_empty_ttl_array_with_hints(fragment_precompiler):
    fragment_precompiler(EmptyTTLArrayWithDummy)
