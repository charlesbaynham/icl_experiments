import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class RedMOTWithClockLight(
    SingleAndorImage,
    FLIRBlueMOTMeasurementMixin,
    ClockSpectroscopyMixin,
    RedMOTWithExperiment,
):
    """
    Image red MOT leaving the clock light on throughout
    """

    def build_fragment(self):
        super().build_fragment()

        self.override_param("spectroscopy_pulse_time", 0.0)
        self.override_param("delay_repumps_after_first_pulse", 0.0)

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.clock_dds.cfg_sw(True)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass


RedMOTWithClockLightExp = make_fragment_scan_exp(RedMOTWithClockLight)
