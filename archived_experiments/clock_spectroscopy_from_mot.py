import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

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


class MOTClockSpectroscopyExp(
    ClockRabiSpectroscopyRedMotMixin, FLIRBlueMOTMeasurementMixin, SingleAndorImage
):
    """
    Basic clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms only
    """


MOTClockSpectroscopy = make_fragment_scan_exp(MOTClockSpectroscopyExp)
