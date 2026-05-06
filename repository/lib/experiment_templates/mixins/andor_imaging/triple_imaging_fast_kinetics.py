import logging

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    TripleImageFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    calculate_grabber_rois,
)

logger = logging.getLogger(__name__)


class TripleImageRedMOTFastKineticsMixin(TripleImageFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """


class TripleImageDipoleTrapFastKineticsMixin(TripleImageFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    This variant implements a default ROI for imaging the forward dipole trap/.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP

    def get_grabber_roi_defaults(self):  # FIXME
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_andor_images,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        )


class TripleImageXXODTFastKineticsMixin(TripleImageFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    This variant implements a two default ROIs for imaging both the forward and backward dipole traps.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_grabber_rois = 6

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP

    def get_grabber_roi_defaults(self):  # FIXME
        forward_rois = calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_andor_images,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        )
        backward_rois = calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_andor_images,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )
        return forward_rois + backward_rois
