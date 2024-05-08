import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)
from repository.lib.fragments.red_mot.red_mot_mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)

logger = logging.getLogger(__name__)


class RedMOTWithClockLight(ClockSpectroscopyMixin, RedMOTWithExperiment):
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
    def do_spectroscopy_hook(self):
        pass

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image ground state atoms
        self.do_first_pulse(andor_exposure)


RedMOTWithClockLightExp = make_fragment_scan_exp(RedMOTWithClockLight)
