import logging

from artiq.experiment import kernel
from artiq.experiment import parallel

from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)

logger = logging.getLogger(__name__)


class FLIRMeasurementMixin(SingleAndorImage, RedMOTWithExperiment):
    """
    Image the atoms using the FLIR cameras

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    This mixin also sets up SingleAndorImage, so the user does not need to
    manually ensure compatibility.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_flir_data_hook`
    """

    @kernel
    def do_imaging_hook(self):
        with parallel:
            self.do_imaging_hook_andor()
            self.do_imaging_hook_flir()

    @kernel
    def do_imaging_hook_flir(self):
        self.camera_interface.trigger()

    @kernel
    def save_flir_data_hook(self):
        # Save blue MOT pics
        self.camera_interface.save_data()
