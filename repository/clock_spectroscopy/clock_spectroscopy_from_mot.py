import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyRedMotMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class MOTClockSpectroscopyNormalizedExp(
    ClockRabiSpectroscopyRedMotMixin,
    FLIRBlueMOTMeasurementMixin,
    NormalisedRedMOTFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
):
    """
    Normalised clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then repeat
    some time later with no atoms.
    """


MOTClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTClockSpectroscopyNormalizedExp
)
