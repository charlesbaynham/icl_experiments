import logging
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsBase,
)

logger = logging.getLogger(__name__)


class NormalisedFastKineticsRedMOTMixin(NormalisedFastKineticsBase):
    """
    Normalised fast kinetics on a red mot
    """
