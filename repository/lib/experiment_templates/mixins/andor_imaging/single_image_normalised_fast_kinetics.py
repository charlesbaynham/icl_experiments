import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsSingleTrapBase,
)

logger = logging.getLogger(__name__)


class SingleImageNormalisedSingleTrapRepumpedSpectroscopyMixin(
    SingleImageNormalisedFastKineticsSingleTrapBase
):
    """
    Single-trap single-image readout for the clock-spectroscopy path.

    This mixin performs a two-pulse fast-kinetics readout on a single trap.
    The first fluorescence pulse images the ground-state population. After a
    short configurable delay, the repumpers turn on so the second pulse images
    the excited-state population. The base class handles ROI placement,
    background subtraction, and result-channel updates.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()

    def time_dropped_before_first_pulse(self):
        return (
            constants.SHELVING_PULSE_CLEAROUT_DURATION
            + constants.CLOCK_SHELVING_PULSE_TIME
            + constants.CLOCK_PI_TIME
        )


class SingleImageNormalisedDoubleTrapRepumpedInterferometryMixin(
    SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase
):
    """
    Double-trap single-image readout for the LMT interferometry path.

    This mixin uses the interferometry timing defined by the base class and
    adds a repump stage after the first fluorescence pulse. The readout then
    extracts background-corrected ground and excited populations for both traps
    from one fast-kinetics image series.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
