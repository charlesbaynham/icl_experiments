"""
This module contains dummy versions of various ARTIQ / NDScan objects. These
exist solely for the purpose of working around ARTIQ's inability to infer the
type of an empty list. You can therefore add one of these into your list in
build() if it's empty, and it won't do anything when called.
"""
from artiq.experiment import HasEnvironment
from artiq.experiment import kernel
from artiq.experiment import TFloat


class DummySUServoFrag(HasEnvironment):
    """
    A dummy class that copies the interface of LibSetSUServoStatic

    This is used by ToggleListOfBeams when an empty list is passed to work
    around the ARTIQ compiler's bad handling of empty lists / arrays.
    """

    def build(self):
        self.setattr_device("core")

    @kernel
    def set_channel_state(self, rf_switch_state=True, enable_iir=True):
        pass


class DummyTTL(HasEnvironment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def set_o(self, state: bool):
        pass


class DummyAD9910(HasEnvironment):
    def build(self):
        self.setattr_device("core")
        self.sw = DummyTTL(self)

    @kernel
    def set(self, frequency: TFloat, amplitude: TFloat):
        pass


class DummyFloatParameterHandle(HasEnvironment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def get(self):
        return 0.0
