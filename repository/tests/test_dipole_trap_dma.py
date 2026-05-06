import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)

logger = logging.getLogger(__name__)


class SimpleClockSpectroscopyFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    BGCorrectedAndorImage,
    DipoleTrapWithExperiment,
):
    """
    SimpleClockSpectroscopy

    As a test, do clock spec with non-normalised imaging
    """


SimpleClockSpectroscopy = make_fragment_scan_exp(SimpleClockSpectroscopyFrag)
