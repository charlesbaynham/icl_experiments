import logging

from artiq.language import kernel

from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)

logger = logging.getLogger(__name__)


class SingleAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~start_of_red_broadband_hook` (from AndorImagingBase)
    * :meth:`~save_grabber_data_hook` (from AndorImagingBase)


    """

    @kernel
    def do_imaging_hook_andor(self):
        # Just image the atoms once
        self.do_pulse()
