import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
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
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class _MeasureNarrowbandMOTFrag(RedMOTWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_experiment", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


class MeasureNarrowbandMOTFrag(
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    SingleAndorImage,
    ConstantBeamsMixin,
    _MeasureNarrowbandMOTFrag,
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
    """


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


class MeasureNarrowbandMOTBGCorrectedWithTrapsFrag(
    BGCorrectedAndorImage,
    FLIRMeasurementMixin,
    ConstantBeamsMixin,
    _MeasureNarrowbandMOTFrag,
):
    """
    Make a narrowband MOT, image twice for BG subtraction with the ANDOR and leave lattice light on
    """


class MeasureNarrowbandMOTBGCorrectedFrag(
    BGCorrectedAndorImage,
    FLIRMeasurementMixin,
    _MeasureNarrowbandMOTFrag,
):
    """
    Make a narrowband MOT, image twice for BG subtraction with the ANDOR
    """


# TODO: This is disabled because it was failing unit tests on master
class MeasureNarrowbandMOTAbsFrag(
    AbsorptionRedMOTMixin,
    _MeasureNarrowbandMOTFrag,
):
    """
    Do absorption imaging with a narrowband MOT
    """


MeasureNarrowbandRedMOT = make_fragment_scan_exp(MeasureNarrowbandMOTFrag)

MeasureNarrowbandRedMOTBGCorrected = make_fragment_scan_exp(
    MeasureNarrowbandMOTBGCorrectedFrag
)
MeasureNarrowbandRedMOTBGCorrectedWithTrap = make_fragment_scan_exp(
    MeasureNarrowbandMOTBGCorrectedWithTrapsFrag
)

MeasureNarrowbandMOTAbs = make_fragment_scan_exp(MeasureNarrowbandMOTAbsFrag)

MeasureNarrowbandRedMOTNoAndor = make_fragment_scan_exp(MeasureNarrowbandMOTNoAndorFrag)
