import logging

from artiq.language import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.cavity_relocking import (
    MonitorAndRelock689and698Mixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class TestCavityRelockingFrag(
    MonitorAndRelock689and698Mixin,
    SingleAndorImage,  # Not actually required, but it's nice to have a picture to look at
    RedMOTWithExperiment,
):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


TestTripleImagingTestCavityRelocking = make_fragment_scan_exp(TestCavityRelockingFrag)
