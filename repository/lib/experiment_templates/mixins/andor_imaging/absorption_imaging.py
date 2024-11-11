from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging_base import (
    AbsorptionImagingBase,
)
from repository.lib import constants
import logging

logger = logging.getLogger(__name__)


class AbsorptionRedMOTMixin(AbsorptionImagingBase):

    def get_default_abs_rois(self):
        x0 = constants.ANDOR_ROI_X0
        y0 = constants.ANDOR_ROI_Y0
        x1 = constants.ANDOR_ROI_X1
        y1 = constants.ANDOR_ROI_Y1
        return [[x0, y0, x1, y1]]


class AbsorptionDipoleTrapMixin(AbsorptionImagingBase):

    def get_default_abs_rois(self):
        x0 = constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0
        y0 = constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0
        x1 = constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1
        y1 = constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1
        return [[x0, y0, x1, y1]]


class AbsorptionDoubleDipoleTrapMixin(AbsorptionImagingBase):

    num_absorption_rois = 2

    def get_default_abs_rois(self):
        default_foward = [
            constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        ]
        default_backward = [
            constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        ]
        return [default_foward, default_backward]
