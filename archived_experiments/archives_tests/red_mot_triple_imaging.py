import logging

from artiq.language import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_basic import (
    TripleImageBasicMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)

logger = logging.getLogger(__name__)


class TestTripleImagingBasic(TripleImageBasicMixin, RedMOTWithExperimentBase):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


class TestTripleImagingKinetics(
    TripleImageRedMOTFastKineticsMixin, RedMOTWithExperimentBase
):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass

    @kernel
    def do_second_pulse(self):
        pass

    @kernel
    def do_third_pulse(self):
        pass


TestTripleImagingBasicExp = make_fragment_scan_exp(TestTripleImagingBasic)
TestTripleImagingKineticsExp = make_fragment_scan_exp(TestTripleImagingKinetics)
