import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


class TripleImageBinnedMixin(RedMOTWithExperiment):
    """
    Implements normalized readout for a :py:class:`~RedMOTWithExperiment`
    experiment with restricted camera ROI

    Contrast with the Fast Kinetics triple imaging.

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excitated state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_data_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_fluoresence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=1e-3,
            unit="ms",
        )
        self.delay_between_fluoresence_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after final fluorescence pulse before background measurement",
            default=10e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

        self.setattr_result("andor_sum_0", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_sum_1", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_sum_2", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.andor_sum_0: FloatChannel
        self.andor_sum_1: FloatChannel
        self.andor_sum_2: FloatChannel
        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    def hook_setup_andor(self):
        """
        Setup the Andor camera to use 3x ROIs since we're expecting fast
        kinetics mode with 3 images

        TODO: Set up Fast Kinetics mode here
        """

        # 1x ROI but we'll trigger three times
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[[0, 0, 512, 512]],  # FIXME
            add_pre_trigger_delay=True,
        )
        self.andor_camera_control: AndorCameraControl

    @kernel
    def start_of_red_broadband_hook(self):
        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        self.andor_camera_control.set_shutter(True)

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image ground state atoms
        self.do_first_pulse(andor_exposure)

        # Image excited state atoms
        delay(self.delay_between_fluoresence_pulses.get())
        self.do_second_pulse(andor_exposure)

        # Take background measurement
        delay(self.delay_before_background_pulse.get())
        self.do_third_pulse(andor_exposure)

    @kernel
    def do_first_pulse(self, andor_exposure):
        self.do_pulse(andor_exposure)

    @kernel
    def do_second_pulse(self, andor_exposure):
        self.do_pulse(andor_exposure)

    @kernel
    def do_third_pulse(self, andor_exposure):
        self.do_pulse(andor_exposure)

    @kernel
    def save_data_hook(self):
        """
        Hook to save data from the Andor camera

        Runs in realtime after imaging is completed.

        We took three images, so read all of them out.
        """
        # Save Andor data
        n = 3
        sums = [0] * n
        means = [0.0] * n

        timeout_mu = self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)

        for i in range(n):
            s = [0]
            m = [0.0]
            self.andor_camera_control.readout_ROIs(s, m, timeout_mu)
            sums[i] = s[0]
            means[i] = m[0]

        self.andor_sum_0.push(sums[0])
        self.andor_sum_1.push(sums[1])
        self.andor_sum_2.push(sums[2])

        bg = means[0] + means[1] - 2 * means[2]
        if bg == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((means[1] - means[2]) / bg)

        self.atom_number.push(means[0] + means[1] - 2 * means[2])
