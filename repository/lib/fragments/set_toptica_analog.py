import logging

from artiq.coredevice.core import Core
from artiq.coredevice.fastino import Fastino
from artiq.language.core import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.constants import TOPTICA_461_ANALOG_SCALE


class SetTopticaAnalogFrag(ExpFragment):
    """
    Use the fastino to offset the topica frequency
    It needs to be told what arc frequency you're currently using
    and it relies on the empirically measured
    scale factor in constants.

    If we want to use this with other lasers, it can be extended
    to take the laser as a parameter and use the appropriate scale factor
    from a list.

    channel is the fastino channel to use
    """

    def build_fragment(self, channel: int = 0):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("fastino0")
        self.fastino0: Fastino

        self.channel = channel

        self.setattr_param(
            "freq_step",
            FloatParam,
            description="Toptica Frequency Step",
            default=0.0,
            unit="MHz",
        )
        self.freq_step: FloatParamHandle

        self.setattr_param(
            "arc_factor",
            FloatParam,
            description="ARC Factor",
            default=0.02,
            unit="V/V",
            scale=1,
        )
        self.arc_factor: FloatParamHandle

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.fastino0.init()

    @kernel
    def step_freq(self, freq: float = None):
        if not freq:
            freq = self.freq_step.get()
        self.fastino0.set_dac(
            self.channel, freq / (TOPTICA_461_ANALOG_SCALE * self.arc_factor.get())
        )

    @kernel
    def run_once(self):
        self.step_freq()
