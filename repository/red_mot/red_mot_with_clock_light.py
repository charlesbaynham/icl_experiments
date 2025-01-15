import logging

from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from numpy import int64

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBaseFrag,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag

logger = logging.getLogger(__name__)


class RedMOTWithClockLight(
    SingleAndorImage,
    FLIRBlueMOTMeasurementMixin,
    RedMOTWithExperiment,
):
    """
    Image red MOT leaving the clock light on throughout
    """

    def build_fragment(self):
        super().build_fragment()

        class _RedMOTWithClockLightFrag(ClockSpectroscopyBaseFrag):
            def build_fragment(self, blue_3d_mot: Blue3DMOTFrag):
                super().build_fragment(blue_3d_mot=blue_3d_mot)

                self.setattr_device("ttl_shutter_repump_679")
                self.ttl_shutter_repump_679: TTLOut

                self.override_param("delay_repumps_after_first_pulse", 0.0)
                self.override_param("clock_delivery_preempt_time", 0.0)

            @kernel
            def start_of_red_broadband_checkpoint(self):
                self.start_of_red_broadband_checkpoint_subfragments()

                delay_mu(int64(self.core.ref_multiplier))

                # Turn off the 679 here so that we can shelve into the clock state
                self.ttl_shutter_repump_679.off()

                # Turn on the clock light and leave it on for the rest of the sequence
                self.clock_dds.cfg_sw(True)

        self.setattr_fragment(
            "_RedMOTWithClockLightFrag",
            _RedMOTWithClockLightFrag,
            blue_3d_mot=self.blue_3d_mot,
        )

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass


RedMOTWithClockLightExp = make_fragment_scan_exp(RedMOTWithClockLight)
