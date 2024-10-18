import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

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
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
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
        """

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
            fast_kinetics_num_shots=3,
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """

        # Image ground state atoms
        self.do_first_pulse()

        # Image excited state atoms
        delay(self.delay_between_fluorescence_pulses.get())
        self.do_second_pulse()

        # Take background measurement
        delay(self.delay_before_background_pulse.get())
        self.do_third_pulse()

    @kernel
    def do_first_pulse(self):
        self.do_pulse()

    @kernel
    def do_second_pulse(self):
        self.do_pulse()

    @kernel
    def do_third_pulse(self):
        self.do_pulse()

    @kernel
    def process_andor_data_hook(self, sums, means):
        atom_number = sums[0] + sums[1] - 2 * sums[2]

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[2]) / atom_number)

        self.atom_number.push(atom_number)
