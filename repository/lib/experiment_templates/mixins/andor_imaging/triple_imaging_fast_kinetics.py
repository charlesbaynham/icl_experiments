import logging

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    TripleImageFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    TripleFKConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    TripleFKDoubleTrapConfig,
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


class TripleImageDipoleTrapFKConfig(TripleFKConfig):
    """TripleFKConfig with dipole-trap-specific FK height/offset defaults."""

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP


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

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            TripleImageDipoleTrapFKConfig,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        )
        self.andor_camera_config: TripleImageDipoleTrapFKConfig
        return f


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

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            TripleFKDoubleTrapConfig,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )
        self.andor_camera_config: TripleFKDoubleTrapConfig
        return f
