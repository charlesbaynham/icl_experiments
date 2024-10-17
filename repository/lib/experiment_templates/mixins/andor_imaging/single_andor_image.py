import logging

from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel

from .imaging_base import AndorImagingBase

logger = logging.getLogger(__name__)
DATASET_NAME = "single_andor_image"


class SingleAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~save_andor_data_hook`
    """

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        # Use default setup
        super().hook_setup_andor()

        # FIXME: These should be moved to andor imaging base and made reusable by other mixins

        self.setattr_result("andor_sum", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean", FloatChannel)
        self.andor_sum: FloatChannel
        self.andor_mean: FloatChannel

        self.setattr_result("andor_sum_slice_x", OpaqueChannel)
        self.setattr_result("andor_sum_slice_y", OpaqueChannel)
        self.setattr_result("andor_image", OpaqueChannel)
        self.andor_sum_slice_x: OpaqueChannel
        self.andor_sum_slice_y: OpaqueChannel
        self.andor_image: OpaqueChannel

    @kernel
    def do_imaging_hook_andor(self):
        # Just image the atoms once
        self.do_pulse()

    @rpc(flags={"async"})
    def _call_camera_rpc(self):
        # FIXME: use the base implementation
        pass

    @kernel
    def save_andor_data_hook(self):
        "Consume all slack and save the photos"

        # FIXME Consider using generic implementation

        self.core.wait_until_mu(now_mu())

        self._call_camera_rpc()

        sums = [0]
        means = [0.0]
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )
        self.andor_sum.push(sums[0])
        self.andor_mean.push(means[0])
