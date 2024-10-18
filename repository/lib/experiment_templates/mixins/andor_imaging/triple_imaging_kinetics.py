import logging

from artiq.experiment import delay
from artiq.experiment import host_only
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

from .imaging_base import ANDOR_MONITOR_DATASET
from .imaging_base import AndorImagingBase

logger = logging.getLogger(__name__)


class TripleImageFastKineticsMixin(AndorImagingBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~save_data_hook`
    """

    num_andor_images = 1
    num_grabber_readouts = 1
    num_grabber_rois = 3

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

        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    def hook_setup_andor(self):
        """
        Setup the Andor camera to use 3x ROIs since we're expecting fast
        kinetics mode with 3 images

        TODO: Set up Fast Kinetics mode here
        """

        # 3x ROIs
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[
                [
                    constants.ANDOR_ROI_X0,
                    i * constants.ANDOR_FAST_KINETICS_HEIGHT,
                    constants.ANDOR_ROI_X1,
                    (i + 1) * constants.ANDOR_FAST_KINETICS_HEIGHT,
                ]
                for i in range(3)
            ],
            add_pre_trigger_delay=True,
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

        # If the andor is in fast kinetics mode and the height of pixels to emit
        # is > 512, it will emit two frames onto Grabber instead of one. The
        # first will be "nonsense" (probably with some digital information that
        # the grabber isn't parsing) and the second will contain all the pixels,
        # up to a max of 1024 high (i.e. the image + storage EMCCDs).
        # See labbook entry 2024-06-11.
        self.andor_requires_storage_frame = (
            constants.ANDOR_FAST_KINETICS_HEIGHT * 3 > constants.ANDOR_SENSOR_HEIGHT
        )
        self.kernel_invariants.add("andor_requires_storage_frame")

    @kernel
    def do_imaging_hook_andor(self):
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

    @kernel
    def save_grabber_data_hook(self):
        """
        Hook to save data from the Andor cameras

        Runs in realtime after imaging is completed
        """

        # Save Andor data
        sums = [0] * 3
        means = [0.0] * 3

        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
            discard_first_frame=,
        )

        self.andor_sum_0.push(sums[0])
        self.andor_sum_1.push(sums[1])
        self.andor_sum_2.push(sums[2])

        bg = means[0] + means[1] - 2 * means[2]
        if bg == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((means[1] - means[2]) / bg)

        self.atom_number.push(means[0] + means[1] - 2 * means[2])

    @host_only
    def update_andor_monitor_hook(self, images):
        """
        Update the andor monitor with an appropriate image
        """
        img_gnd = images[0]
        # img_excited = images[1]
        img_bg = images[2]

        # TODO: Consider how to plot the excited atoms here
        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            img_gnd - img_bg,
            broadcast=True,
            persist=False,
            archive=False,
        )
