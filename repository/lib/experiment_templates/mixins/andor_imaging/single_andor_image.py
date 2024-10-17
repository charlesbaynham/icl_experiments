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

    @kernel
    def do_imaging_hook_andor(self):
        # Just image the atoms once
        self.do_pulse()

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
