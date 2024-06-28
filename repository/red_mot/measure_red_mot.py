import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTBase
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.fragments.red_mot.red_mot_mixins.constant_lattice import (
    ConstantLatticeMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.dipole_trap import DipoleTrapMixin
from repository.lib.fragments.red_mot.red_mot_mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)

logger = logging.getLogger(__name__)


class _MeasureNarrowbandMOTFrag(ConstantLatticeMixin, RedMOTWithExperiment):
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
    FLIRMeasurementMixin, SingleAndorImage, _MeasureNarrowbandMOTFrag
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
    """

    pass


class MeasureDipoleTrapFrag(
    DipoleTrapMixin, FLIRMeasurementMixin, SingleAndorImage, _MeasureNarrowbandMOTFrag
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
MeasureDipoleTrap = make_fragment_scan_exp(MeasureDipoleTrapFrag)
