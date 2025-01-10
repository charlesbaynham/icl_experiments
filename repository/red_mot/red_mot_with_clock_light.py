import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
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
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

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

        self.override_param("delay_repumps_after_first_pulse", 0.0)

        class _RedMOTWithClockLightFrag(RedMOTCheckpoints):
            def build_fragment(self, clock_dds: AD9912):
                self.setattr_device("core")
                self.core: Core

                self.setattr_device("ttl_shutter_repump_679")
                self.ttl_shutter_repump_679: TTLOut

                self.clock_dds = clock_dds
                self.kernel_invariants.add("clock_dds")

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                # Turn on the clock light immediately and leave it throughout
                self.clock_dds.cfg_sw(True)

            @kernel
            def start_of_red_broadband_checkpoint(self):
                self.start_of_red_broadband_checkpoint_subfragments()

                delay_mu(int64(self.core.ref_multiplier))

                # Turn off the 679 here so that we can shelve into the clock state
                self.ttl_shutter_repump_679.off()

        self.setattr_fragment(
            "_RedMOTWithClockLightFrag",
            _RedMOTWithClockLightFrag,
            clock_dds=self.clock_dds,
        )

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass


RedMOTWithClockLightExp = make_fragment_scan_exp(RedMOTWithClockLight)
