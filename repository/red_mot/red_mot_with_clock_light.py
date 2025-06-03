import logging

from artiq.coredevice.ttl import TTLOut
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from numpy import int64

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class RedMOTWithClockLight(
    SingleAndorImage,
    FLIRBlueMOTMeasurementMixin,
    ClockSpectroscopyBase,
    RedMOTWithExperiment,
):
    """
    Image red MOT leaving the clock light on throughout
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("ttl_shutter_repump_679")
        self.ttl_shutter_repump_679: TTLOut

        self.override_param("delay_repumps_after_first_pulse", 0.0)

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()

        # Turn on the click light immediately and leave it throughout
        self.clock_dds.cfg_sw(True)

    @kernel
    def start_of_red_broadband_hook(self):
        self.start_of_red_broadband_hook_imaging_base()

        delay_mu(int64(self.core.ref_multiplier))

        # Turn off the 679 here so that we can shelve into the clock state
        self.ttl_shutter_repump_679.off()

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass


RedMOTWithClockLightExp = make_fragment_scan_exp(RedMOTWithClockLight)
