import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)

logger = logging.getLogger(__name__)


class BGCorrectedAndorImage(RedMOTWithExperiment):
    """
    Image with a single fluorescence pulse using the Andor camera then take another for background subtraction

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_data_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle

        self.setattr_result("andor_mean_bg_corrected", FloatChannel)
        self.andor_mean_bg_corrected: FloatChannel

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image atoms
        self.do_pulse(andor_exposure)

        # Drop them
        self.blue_3d_mot.chamber_2_field_setter.set_mot_gradient(0.0)

        delay(self.delay_before_bg_pulse.get())

        # Image background with no atoms
        self.do_pulse(andor_exposure)

    @kernel
    def save_data_hook(self):
        "Consume all slack and save the photos"
        self.core.wait_until_mu(now_mu())

        sum_atoms = [0]
        mean_atoms = [0.0]
        sum_bg = [0]
        mean_bg = [0.0]

        self.andor_camera_control.readout_ROIs(
            sum_atoms,
            mean_atoms,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )
        self.andor_camera_control.readout_ROIs(
            sum_bg,
            mean_bg,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )

        self.andor_sum.push(sum_atoms[0])
        self.andor_mean.push(mean_atoms[0])
        self.andor_mean_bg_corrected.push(mean_atoms[0] - mean_bg[0])
