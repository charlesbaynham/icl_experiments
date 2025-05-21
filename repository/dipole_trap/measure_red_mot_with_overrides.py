import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

import repository.lib.constants as constants
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.red_mot.measure_red_mot import MeasureNarrowbandMOTBGCorrectedFrag

logger = logging.getLogger(__name__)

# Save some default settings which load dipole traps in the top / bottom traps.
# This file will be regularly updated over time. It breaks the rule about
# putting physics facts in "constants.py" because these are not really
# constants, they're just an easier way to set values for a given experiment
# without using the clicky ndscan interface. This is a hack.


def make_experiment(
    name: str,
    chamber_2_bias_x,
    chamber_2_bias_y,
    chamber_2_bias_z,
    chamber_2_mot_current_start,
    chamber_2_mot_current_end,
    roi_0_x0,
    roi_0_x1,
    roi_0_y0,
    roi_0_y1,
):
    pass

    class Exp(ExponentialDecayMixin, MeasureNarrowbandMOTBGCorrectedFrag):
        def build_fragment(self):
            super().build_fragment()

            self.setattr_param_rebind(
                "narrowband_bias_x", self.red_mot, default=chamber_2_bias_x
            )
            self.setattr_param_rebind(
                "narrowband_bias_y", self.red_mot, default=chamber_2_bias_y
            )
            self.setattr_param_rebind(
                "narrowband_bias_z", self.red_mot, default=chamber_2_bias_z
            )

            self.setattr_param_rebind(
                "chamber_2_mot_current_start",
                self.red_mot.narrow_red_compression_phase,
                default=chamber_2_mot_current_start,
            )
            self.setattr_param_rebind(
                "chamber_2_mot_current_end",
                self.red_mot.narrow_red_compression_phase,
                default=chamber_2_mot_current_end,
            )

            self.setattr_param_rebind(
                "roi_0_x0",
                self.andor_camera_control,
                default=roi_0_x0,
            )
            self.setattr_param_rebind(
                "roi_0_x1",
                self.andor_camera_control,
                default=roi_0_x1,
            )
            self.setattr_param_rebind(
                "roi_0_y0",
                self.andor_camera_control,
                default=roi_0_y0,
            )
            self.setattr_param_rebind(
                "roi_0_y1",
                self.andor_camera_control,
                default=roi_0_y1,
            )

    Exp.__name__ = name
    Exp.__qualname__ = name

    return make_fragment_scan_exp(Exp, max_rtio_underflow_retries=0)


LoadBackwardDipoleTrap = make_experiment(
    "LoadBackwardDipoleTrap",
    chamber_2_bias_x=constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_X,
    chamber_2_bias_y=constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_Y,
    chamber_2_bias_z=constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_Z,
    chamber_2_mot_current_start=3,
    chamber_2_mot_current_end=constants.XODT_SINGLE_NARROWBAND_COMPRESSION_GRADIENT,
    roi_0_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
    roi_0_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
    roi_0_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
    roi_0_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
)


LoadForwardDipoleTrap = make_experiment(
    "LoadForwardDipoleTrap",
    chamber_2_bias_x=constants.RED_NARROWBAND_BIAS_FIELD_X,
    chamber_2_bias_y=constants.RED_NARROWBAND_BIAS_FIELD_Y,
    chamber_2_bias_z=constants.RED_NARROWBAND_BIAS_FIELD_Z,
    chamber_2_mot_current_start=3,
    chamber_2_mot_current_end=constants.XODT_SINGLE_NARROWBAND_COMPRESSION_GRADIENT,
    roi_0_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
    roi_0_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
    roi_0_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
    roi_0_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
)
