import logging

from artiq.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class TestNormalisedFastKinetics(
    NormalisedRedMOTFastKineticsMixin, RedMOTWithExperiment
):
    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass


TestNormalisedFastKineticsExp = make_fragment_scan_exp(TestNormalisedFastKinetics)
