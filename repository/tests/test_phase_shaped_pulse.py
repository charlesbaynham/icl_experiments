import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import AD9910

from artiq.language import delay_mu
from artiq.language import delay
from artiq.language import kernel
from numpy import int64
from ndscan.experiment import *

from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment import ExpFragment
from repository.lib.fragments.pulse_shaping import PhaseStepPulse, PhaseRampPulse

from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    CLOCK_BEAM_INFO,
)

logger = logging.getLogger(__name__)


class TestPhaseShapedPulse(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.lo_dds: AD9910 = self.get_device("urukul2_ch3")


        self.setattr_fragment(
            "shaped_pulse",
            PhaseRampPulse,
            ad9910_name=CLOCK_BEAM_INFO.urukul_device,
        )
        self.shaped_pulse: PhaseRampPulse

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.shaped_pulse.cpld.init(blind=False)
        self.core.break_realtime()
        self.shaped_pulse.dds.init(blind=False)
        self.core.break_realtime()
        self.lo_dds.init(blind=False)
        self.core.break_realtime()
        self.shaped_pulse.dds.set(frequency=CLOCK_BEAM_INFO.frequency)

        self.core.break_realtime()

        self.lo_dds.set(frequency=CLOCK_BEAM_INFO.frequency)
        self.lo_dds.sw.on()

        delay(100e-3)

        self.shaped_pulse.prepare_pulse(frequency=CLOCK_BEAM_INFO.frequency)

        delay(100e-3)

        self.shaped_pulse.trigger_pulse()
        delay(100e-3)

        self.shaped_pulse.disable_ram_mode()
        self.lo_dds.sw.off()

TestPhaseShapedPulseExp = make_fragment_scan_exp(TestPhaseShapedPulse)
