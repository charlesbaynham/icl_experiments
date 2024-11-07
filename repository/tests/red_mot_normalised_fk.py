import logging

from artiq.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.red_mot.measure_red_mot import _MeasureNarrowbandMOTFrag
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)

logger = logging.getLogger(__name__)


class TestNormalisedFastKinetics(
    NormalisedRedMOTFastKineticsMixin, _MeasureNarrowbandMOTFrag
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
    Do two fast kinetics series to for normalised readout
    """


TestNormalisedFastKineticsExp = make_fragment_scan_exp(TestNormalisedFastKinetics)
