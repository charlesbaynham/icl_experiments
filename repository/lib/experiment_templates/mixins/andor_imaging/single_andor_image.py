import logging

from artiq.experiment import kernel

from .imaging_base import AndorImagingBase

logger = logging.getLogger(__name__)


class SingleAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    @kernel
    def do_imaging_hook_andor(self):
        # Just image the atoms once
        self.do_pulse()
