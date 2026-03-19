import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.red_mot.measure_red_mot import _MeasureNarrowbandMOTFrag

logger = logging.getLogger(__name__)


class MeasureNarrowbandMOTNoAndorFrag(
    FLIRMeasurementMixin,
    SingleAndorImage,
    ExponentialDecayMixin,
    ConstantBeamsMixin,
    _MeasureNarrowbandMOTFrag,
):
    """
    Make a narrowband MOT, image with the FLIR and leave lattice light on
    """

    keep_andor_shutter_closed = True


MeasureNarrowbandRedMOTNoAndor = make_fragment_scan_exp(MeasureNarrowbandMOTNoAndorFrag)
