import logging

from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)

logger = logging.getLogger(__name__)


class TripleImageBasicMixin(AndorImagingBase):
    """
    Implements normalized readout for a :py:class:`~RedMOTWithExperimentBase`
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
    * :meth:`~update_andor_monitor_hook`
    * :meth:`~process_andor_data_hook`
    """

    num_andor_images = 3

    num_grabber_readouts = 3
    num_grabber_rois = 1

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_fluorescence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=10e-3,
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

    @kernel
    def process_grabber_data_hook(self, sums, means):
        bg = sums[0] + sums[1] - 2 * sums[2]

        if bg == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[2]) / bg)

        self.atom_number.push(sums[0] + sums[1] - 2 * sums[2])
