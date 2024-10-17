import logging

from artiq.experiment import delay, host_only
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from .imaging_base import AndorImagingBase, ANDOR_MONITOR_DATASET

logger = logging.getLogger(__name__)


class TripleImageBasicMixin(AndorImagingBase):
    """
    Implements normalized readout for a :py:class:`~RedMOTWithExperiment`
    experiment by just taking multiple images.

    Contrast with the Fast Kinetics triple imaging.

    TODO: Add camera ROI restriction to speed up acquisition.

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_data_hook`
    """

    num_andor_images = 3

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_fluorescence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=1e-3,
            unit="ms",
        )
        self.delay_between_fluorescence_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after final fluorescence pulse before background measurement",
            default=10e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

    def hook_setup_andor(self):
        # Use the default ROI setup
        super().hook_setup_andor()

        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """

        # Image ground state atoms
        self.do_pulse()

        # Image excited state atoms
        delay(self.delay_between_fluorescence_pulses.get())
        self.do_pulse()

        # Take background measurement
        delay(self.delay_before_background_pulse.get())
        self.do_pulse()

    @host_only
    def update_andor_monitor_hook(self):
        """
        Update the andor monitor with an appropriate image
        """
        try:
            img_gnd = self.andor_images[0].sink.get_last()
            img_excited = self.andor_images[1].sink.get_last()
            img_bg = self.andor_images[2].sink.get_last()
        except AttributeError:
            img_gnd = [[0.0]]
            img_excited = [[0.0]]
            img_bg = [[0.0]]

        if img_gnd is None:
            img_gnd = [[0.0]]
            img_excited = [[0.0]]
            img_bg = [[0.0]]

        # TODO: Consider how to plot the excited atoms here
        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            img_gnd - img_bg,
            broadcast=True,
            persist=False,
            archive=False,
        )

    @kernel
    def save_andor_data_hook(self):
        """
        Hook to save data from the Andor camera

        Runs in realtime after imaging is completed.

        We took three images, so read all of them out.
        """
        # FIXME: Decide how to integrate this with AndorImagingBase

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
