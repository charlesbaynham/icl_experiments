import logging

from artiq.language import kernel

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class ShelveInBlueMOTMixin(RedMOTWithExperiment):
    """
    Add shelving during blue MOT to protect cold atoms from loss mechanisms
    """

    def build_fragment(self):
        super().build_fragment()

    @kernel
    def before_blue_mot_hook(self):
        self.red_mot.prepare_for_broadband_phase()
