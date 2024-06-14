import logging

from artiq.experiment import delay
from artiq.experiment import kernel

from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


class FLIRBlueMOTMeasurementMixin(RedMOTWithExperiment):
    """
    Image the blue MOT using the FLIR cameras

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~end_of_broadband_mot_hook`
    * :meth:`~save_flir_data_hook`
    """

    @kernel
    def end_of_broadband_mot_hook(self):
        # The FLIR cameras are not useful for the final imaging, so use them to
        # image the blue MOT instead
        delay(-self.red_broadband_time.get() - 10e-3)
        self.camera_interface.trigger()
        delay(+self.red_broadband_time.get() + 10e-3)

    @kernel
    def save_flir_data_hook(self):
        # Save blue MOT pics
        self.camera_interface.save_data()
