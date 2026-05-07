import logging

from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    DroptimeInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    DroptimeSpectroscopyMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    RepumpingWith679Mixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    RepumpingWithClockMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedDoubleTrapBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedSingleTrapBase,
)

logger = logging.getLogger(__name__)


class SingleImageNormalisedSingleTrapRepumpedSpectroscopyMixin(
    RepumpingWith679Mixin,
    DroptimeSpectroscopyMixin,
    SingleImageNormalisedSingleTrapBase,
):
    """
    Single-trap single-image readout for the clock-spectroscopy path.

    This mixin performs a two-pulse fast-kinetics readout on a single trap.
    The first fluorescence pulse images the ground-state population. After a
    short configurable delay, the repumpers turn on so the second pulse images
    the excited-state population. The base class handles ROI placement,
    background subtraction, and result-channel updates.
    """


class SingleImageNormalisedSingleTrapClockPulseSpectroscopyMixin(
    RepumpingWithClockMixin,
    DroptimeSpectroscopyMixin,
    SingleImageNormalisedSingleTrapBase,
):
    """
    Single-trap single-image readout for the clock-spectroscopy path using a
    clock pi pulse between the two imaging pulses.

    The first fluorescence pulse images the ground-state population. After a
    short configurable delay, a clock pulse transfers the excited-state atoms
    into the fluorescing state so the second pulse images the excited-state
    population.
    """


class SingleImageNormalisedDoubleTrapRepumpedInterferometryMixin(
    RepumpingWith679Mixin,
    DroptimeInterferometryMixin,
    SingleImageNormalisedDoubleTrapBase,
):
    """
    Double-trap single-image readout for the LMT interferometry path.

    This mixin uses the interferometry timing defined by the base class and
    adds a repump stage after the first fluorescence pulse. The readout then
    extracts background-corrected ground and excited populations for both traps
    from one fast-kinetics image series.
    """


class SingleImageNormalisedDoubleTrapClockPulseInterferometryMixin(
    RepumpingWithClockMixin,
    DroptimeInterferometryMixin,
    SingleImageNormalisedDoubleTrapBase,
):
    """
    Double-trap single-image readout for the LMT interferometry path using a
    clock pi pulse between the two imaging pulses.

    The first fluorescence pulse images the ground-state population. After a
    short configurable delay, a clock pulse transfers the excited-state atoms
    into the fluorescing state so the second pulse measures the excited-state
    population for both traps.
    """
