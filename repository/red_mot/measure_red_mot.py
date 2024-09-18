import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
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
from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class _MeasureNarrowbandMOTFrag(ConstantBeamsMixin, RedMOTWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_spectroscopy", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def do_spectroscopy_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


class MeasureNarrowbandMOTFrag(
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    SingleAndorImage,
    _MeasureNarrowbandMOTFrag,
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
    """

    pass


class MeasureNarrowbandMOTBGCorrectedFrag(
    BGCorrectedAndorImage, _MeasureNarrowbandMOTFrag
):
    """
    Make a narrowband MOT, image twice for BG subtraction with the ANDOR and leave lattice light on
    """

    pass


MeasureNarrowbandRedMOT = make_fragment_scan_exp(MeasureNarrowbandMOTFrag)

MeasureNarrowbandRedMOTBGCorrected = make_fragment_scan_exp(
    MeasureNarrowbandMOTBGCorrectedFrag
)
