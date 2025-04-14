import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
from scipy.stats import beta

from repository.lib.fragments.pulse_shaping import ShapedPulse


class BetaShapedPulse(ShapedPulse):
    def build_fragment(self, *args, **kwargs):
        self.setattr_param(
            "alpha",
            FloatParam,
            description="Alpha parameter for Beta distribution",
            default=2.0,
            min=0.1,
            max=10.0,
        )
        self.alpha: FloatParamHandle

        self.setattr_param(
            "beta_param",
            FloatParam,
            description="Beta parameter for Beta distribution",
            default=2.0,
            min=0.1,
            max=10.0,
        )
        self.beta_param: FloatParamHandle

        # Kernel params
        self._old_alpha = -1.0
        self._old_beta = -1.0

        return super().build_fragment(*args, **kwargs)

    def generate_amplitudes_and_phases(self, n_words) -> np.ndarray:
        """
        Use the Beta function to generate a smooth range of amplitudes using scipy.stats.beta:
        https://en.wikipedia.org/wiki/Beta_function

        The output will be normalized to 0 -> +1.
        """

        t = np.linspace(0, 1, n_words)
        amplitude = beta(self.alpha.get(), self.beta_param.get()).pdf(t)

        amplitude /= max(amplitude)

        phase = np.zeros_like(amplitude)

        return amplitude, phase

    @kernel
    def is_recalc_needed(self) -> bool:
        """
        Check if the alpha or beta parameters have changed.
        """

        return_value = False

        if (
            self.alpha.get() != self._old_alpha
            or self.beta_param.get() != self._old_beta
        ):
            return_value = True

        self._old_alpha = self.alpha.get()
        self._old_beta = self.beta_param.get()

        return return_value


class _TestShapedPulseBase(ExpFragment):
    the_pulse = None

    def build_fragment(self):
        self.setattr_fragment(
            "shaped_pulse", self.the_pulse, ad9910_name="urukul9910_aom_698_up_switch"
        )
        self.shaped_pulse: ShapedPulse

        self.setattr_device("core")
        self.core: Core

        self.ttl_trigger: TTLOut = self.get_device("ttl_shutter_debugging_trigger")

        self.first_run = False

    @kernel
    def run_once(self):
        if self.first_run:
            self.first_run = False
            self.core.break_realtime()
            self.ttl_trigger.off()
            self.shaped_pulse.cpld.init(blind=False)
            self.core.break_realtime()
            self.shaped_pulse.dds.init(blind=False)
            self.core.break_realtime()
            self.shaped_pulse.dds.set(10e6)

        self.core.break_realtime()
        self.shaped_pulse.prepare_pulse(frequency=10e6)

        self.core.break_realtime()
        self.ttl_trigger.pulse(1e-6)
        self.shaped_pulse.trigger_pulse()
        self.shaped_pulse.disable_ram_mode()


class TestBetaShapedPulseFrag(_TestShapedPulseBase):
    the_pulse = BetaShapedPulse


class TestShapedBlackmanPulse(_TestShapedPulseBase):
    the_pulse = BlackmanShapedPulse


class TestShapedPulseOnAdjacent(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment(
            "shaped_pulse", BetaShapedPulse, ad9910_name="urukul0_ch0"
        )
        self.shaped_pulse: ShapedPulse

        self.setattr_device("core")
        self.core: Core

        self.monitor_dds: AD9910 = self.get_device("urukul0_ch0")
        self.ttl_trigger: TTLOut = self.get_device("ttl4")

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.ttl_trigger.off()

        self.shaped_pulse.cpld.init(blind=False)
        self.core.break_realtime()
        self.shaped_pulse.dds.init(blind=False)
        self.core.break_realtime()
        self.monitor_dds.init(blind=False)
        self.core.break_realtime()
        self.shaped_pulse.dds.set(10e6)

        self.core.break_realtime()

        self.ttl_trigger.pulse(1e-6)

        self.monitor_dds.set(10e6)
        self.monitor_dds.sw.on()

        delay(100e-3)

        self.shaped_pulse.prepare_pulse(frequency=10e6)

        delay(100e-3)

        self.shaped_pulse.trigger_pulse()
        delay(100e-3)
        # self.shaped_pulse.trigger_pulse()

        self.shaped_pulse.disable_ram_mode()
        self.monitor_dds.sw.off()


TestBetaShapedPulseExp = make_fragment_scan_exp(
    TestBetaShapedPulseFrag, max_rtio_underflow_retries=0
)
TestShapedBlackmanPulseExp = make_fragment_scan_exp(
    TestShapedBlackmanPulse, max_rtio_underflow_retries=0
)
TestShapedPulseOnAdjacentExp = make_fragment_scan_exp(TestShapedPulseOnAdjacent)
