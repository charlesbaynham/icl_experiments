import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.dipole_trap import DipoleTrapMixin
from repository.lib.fragments.red_mot.red_mot_mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)

logger = logging.getLogger(__name__)


class MeasureDipoleTrapFrag(
    DipoleTrapMixin, FLIRMeasurementMixin, SingleAndorImage, RedMOTWithExperiment
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
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
