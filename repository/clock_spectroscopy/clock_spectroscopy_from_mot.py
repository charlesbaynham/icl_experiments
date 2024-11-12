import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyRedMotMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class MOTClockSpectroscopyExp(
    ClockRabiSpectroscopyRedMotMixin, FLIRBlueMOTMeasurementMixin, SingleAndorImage
):
    """
    Basic clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms only
    """


class MOTClockSpectroscopyNormalizedExp(
    ClockRabiSpectroscopyRedMotMixin,
    FLIRBlueMOTMeasurementMixin,
    NormalisedRedMOTFastKineticsMixin,
):
    """
    Normalised clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then repeat
    some time later with no atoms.
    """


class MOTPumpedClockSpectroscopyNormalizedExp(
    ClockRabiSpectroscopyRedMotMixin,
    ClockShelvingAndClearoutRedMOTMixin,
    FLIRBlueMOTMeasurementMixin,
    TripleImageRedMOTFastKineticsMixin,
):
    """
    Normalised clock spectroscopy from a red MOT with clock shelving

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM.

    * Before spectroscopy, do a clock pulse and blast away residual ground-state
    atoms.

    * Do a clock pulse.

    * Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """


MOTClockSpectroscopy = make_fragment_scan_exp(MOTClockSpectroscopyExp)
MOTClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTClockSpectroscopyNormalizedExp
)
MOTPumpedClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTPumpedClockSpectroscopyNormalizedExp
)
