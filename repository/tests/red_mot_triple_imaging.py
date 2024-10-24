import logging

from artiq.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_basic import (
    TripleImageBasicMixin,
)

from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class TestTripleImagingBasic(TripleImageBasicMixin, RedMOTWithExperiment):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


class TestTripleImagingKinetics(TripleImageFastKineticsMixin, RedMOTWithExperiment):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


TestTripleImagingBasicExp = make_fragment_scan_exp(TestTripleImagingBasic)
TestTripleImagingKineticsExp = make_fragment_scan_exp(TestTripleImagingKinetics)
