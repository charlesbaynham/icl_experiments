import logging

from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.red_mot.measure_red_mot import _MeasureNarrowbandMOTFrag

logger = logging.getLogger(__name__)


class TestNormalisedFastKinetics(
    NormalisedRedMOTFastKineticsMixin, _MeasureNarrowbandMOTFrag
):
    """
    Test normalised fast kinetics
    """


TestNormalisedFastKineticsExp = make_fragment_scan_exp(TestNormalisedFastKinetics)
