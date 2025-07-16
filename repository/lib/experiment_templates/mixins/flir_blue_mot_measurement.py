import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement

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

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "camera_interface", DualCameraMeasurement, hardware_trigger=True
        )
        self.camera_interface: DualCameraMeasurement

        self.camera_interface.image_vertical_mean.display_hints["priority"] = -1

        self.setattr_param_rebind(
            "exposure_horiz",
            self.camera_interface,
            "exposure_horiz",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Horizontal camera exposure time",
            unit="us",
        )
        self.setattr_param_rebind(
            "exposure_vert",
            self.camera_interface,
            "exposure_vert",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Vertical camera exposure time",
            unit="us",
        )
        self.exposure_horiz: FloatParamHandle
        self.exposure_vert: FloatParamHandle

    @kernel
    def end_of_blue_3d_mot_loading_hook(self):
        # The FLIR cameras are not useful for the final imaging, so use them to
        # image the blue MOT instead
        delay(-10e-3)
        self.camera_interface.trigger()
        delay(10e-3)

    @kernel
    def save_flir_data_hook(self):
        # Save blue MOT pics
        self.camera_interface.save_data()
