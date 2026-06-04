import logging

from artiq.language import kernel
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement

logger = logging.getLogger(__name__)


class FLIRMeasurementMixin(RedMOTWithExperimentBase):
    """
    Image the atoms using the FLIR cameras

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_flir`
    * :meth:`~save_flir_data_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "camera_interface", DualCameraMeasurement, hardware_trigger=True
        )
        self.camera_interface: DualCameraMeasurement

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
    def do_imaging_hook_flir(self):
        self.camera_interface.trigger()

    @kernel
    def save_flir_data_hook(self):
        # Save blue MOT pics
        self.camera_interface.save_data()
