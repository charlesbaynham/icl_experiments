import logging

from ndscan.experiment.result_channels import FloatChannel

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging_base import (
    AbsorptionImagingBase,
)

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

    def hook_setup_andor_results(self):
        super().hook_setup_andor_results()
        self.setattr_result(
            "atom_number_ratio",
            FloatChannel,
            display_hints={"priority": -1},
        )
        self.atom_number_ratio: FloatChannel

    def process_andor_image_hook(self, images):
        super().process_andor_image_hook(images)
        atoms_img = images[0]
        light_img = images[1]
        bg_img = images[2]
        Ns, _, _, _ = self.calc_atom_number(atoms_img, light_img, bg_img)
        ratio = Ns[0] / Ns[1]
        self.atom_number_ratio.push(ratio)
