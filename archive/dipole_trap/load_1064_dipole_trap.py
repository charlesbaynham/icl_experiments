import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.dipole_trap import DipoleTrapMixin
from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class MeasureDipoleTrapFrag(DipoleTrapMixin, SingleAndorImage, RedMOTWithExperiment):
    """
    Make a dipole trap and image it with the Andor
    """

    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_spectroscopy", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def do_spectroscopy_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


MeasureDipoleTrap = make_fragment_scan_exp(MeasureDipoleTrapFrag)
