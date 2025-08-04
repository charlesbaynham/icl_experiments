from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import Fragment
from pyaion.fragments.ad9910_ramper import AD9910Ramper

import repository.lib.constants as constants
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)

OFFSET_FREQ = 80e6


class ClockOPLLController(Fragment):
    """
    Methods for controlling the clock OPLL
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

        self.setattr_fragment(
            "clock_frequency_ramper",
            AD9910Ramper,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
        )
        self.clock_frequency_ramper: AD9910Ramper

        self.clock_OPLL_offset: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device
        )
        # self.kernel_invariants.add("clock_opll_offset")

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Ensure the clock's OPLL offset RF switch is on and the frequency is
        # correct. These are glitch free, so we do them each time
        self.core.break_realtime()
        self.clock_OPLL_offset.set(OFFSET_FREQ)
        self.clock_OPLL_offset.sw.on()
