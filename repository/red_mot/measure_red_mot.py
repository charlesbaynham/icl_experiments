import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTBase
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)


logger = logging.getLogger(__name__)


class MeasureBBRedMOTFrag(RedMOTBase):
    @kernel
    def run_once(self):
        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()
        self._expand_and_image()
        self._save_data()


class MeasureNarrowbandMOTFrag(SingleAndorImage, RedMOTWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_spectroscopy", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def do_spectroscopy_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(
    MeasureNarrowbandMOTFrag, max_rtio_underflow_retries=0
)
