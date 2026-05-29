import logging

from artiq.language import kernel

from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.external_trigger import ExternalTriggerFrag

logger = logging.getLogger(__name__)


class External50HzTriggerMixin(RedMOTWithExperimentBase):
    """
    Adds automatic external triggering for the experiment

    This will make timing of the rest of the sequence deterministic with respect
    to the external trigger (assuming we have no break_realtimes() in the
    sequence, which we should never have).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "external_trigger",
            ExternalTriggerFrag,
            ttl_name="ttl_50hz_trigger",
            auto_wait=False,
        )
        self.external_trigger: ExternalTriggerFrag

    @kernel
    def pre_sequence_hook(self):
        """
        Wait for the external trigger before starting the sequence, but after
        all setup is done and we're ready to run the sequence.
        """
        self.external_trigger.wait_for_trigger()
