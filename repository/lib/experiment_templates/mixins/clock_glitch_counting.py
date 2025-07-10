import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import host_only
from artiq.experiment import rpc
from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.devices.clock_glitch_filter import ClockGlitchFilter
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)

logger = logging.getLogger(__name__)


class ClockGlitchFilterFrag(Fragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("clock_glitch_filter")
        self.clock_glitch_filter: ClockGlitchFilter

        self.setattr_device("ttl_clock_glitch_counter")
        self.ttl_clock_glitch_counter: TTLOut

        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "gate_threshold",
            FloatParam,
            description="TTL threshold for gating the clock glitch filter",
            default=constants.CLOCK_GLITCH_FILTER_GATE_THRESHOLD,
            unit="V",
        )
        self.gate_threshold: FloatParamHandle

        self.setattr_param(
            "glitch_threshold",
            FloatParam,
            description="Threshold for counting a glitch",
            default=constants.CLOCK_GLITCH_FILTER_GLITCH_THRESHOLD,
            unit="V",
        )
        self.glitch_threshold: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        # Initiate the device with default settings
        config = self.clock_glitch_filter.set_config(
            glitch_threshold=self.glitch_threshold.get(),
            gate_threshold=self.gate_threshold.get(),
        )

        logger.debug("Set clock glitch filter config: %s", config)

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Setup the mask
        self.core.break_realtime()
        self.ttl_clock_glitch_counter.output()
        self.ttl_clock_glitch_counter.off()

        # Clear the count of glitches
        self.clear_glitch_count()

    @kernel
    def start_counting_glitches(self):
        """
        Start counting glitches.
        """
        self.ttl_clock_glitch_counter.on()

    @kernel
    def stop_counting_glitches(self):
        """
        Stop counting glitches.
        """
        self.ttl_clock_glitch_counter.off()

    @rpc
    def clear_glitch_count(self):
        self.clock_glitch_filter.get_num_glitches()

    @host_only
    def get_num_glitches(self) -> int:
        """
        Get the number of glitches counted.

        Must be called from the host (i.e. via an RPC).
        """
        return self.clock_glitch_filter.get_num_glitches()


class ClockGlitchCounterMixin(ClockInterferometryBase):
    """
    Adds counting of clock glitches during clock interferometry

    Only works for clock interferometry for now, but could easily be adapted for
    general clock spectroscopy. The glitch counter supports counting during
    multiple pulses so we could only count when the clock light is on, however
    this code instead counts during the whole interferometry sequence from when
    the first pulse starts to when the final pulse ends.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~start_interferometry_hook`
    * :meth:`~end_interferometry_hook`
    * :meth:`~host_functions_after_experiment_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("clock_glitch_filter", ClockGlitchFilterFrag)
        self.clock_glitch_filter: ClockGlitchFilterFrag

        self.setattr_result(
            "clock_glitch_filter_num_glitches",
            FloatChannel,
            display_hints={"priority": -1},
        )
        self.clock_glitch_filter_num_glitches: FloatChannel

    @kernel
    def start_interferometry_hook(self):
        self.clock_glitch_filter.start_counting_glitches()

    @kernel
    def end_interferometry_hook(self):
        self.clock_glitch_filter.stop_counting_glitches()

    @kernel
    def host_functions_after_experiment_hook(self):
        self.host_functions_after_experiment_hook_default()
        self.host_functions_after_experiment_hook_glitch_counter()

    @kernel
    def host_functions_after_experiment_hook_glitch_counter(self):
        self.count_glitches()

    @rpc(flags={"async"})
    def count_glitches(self):
        num_glitches = self.clock_glitch_filter.get_num_glitches()
        self.clock_glitch_filter_num_glitches.push(num_glitches)
