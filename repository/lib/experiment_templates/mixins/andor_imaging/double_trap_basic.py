import logging

from .single_andor_image import SingleAndorImage

logger = logging.getLogger(__name__)
DATASET_NAME = "single_andor_image"


class DoubleTrapImagingBasic(SingleAndorImage):
    """
    Image two traps with a single fluorescence pulse

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    num_andor_images = 1
    num_grabber_readouts = 1
    num_grabber_rois = 2
