import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

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

    class Exp(MeasureNarrowbandMOTBGCorrectedFrag):
        def build_fragment(self):
            super().build_fragment()

            self.setattr_param_rebind(
                "chamber_2_bias_x", self.blue_3d_mot, default=chamber_2_bias_x
            )
            self.setattr_param_rebind(
                "chamber_2_bias_y", self.blue_3d_mot, default=chamber_2_bias_y
            )
            self.setattr_param_rebind(
                "chamber_2_bias_z", self.blue_3d_mot, default=chamber_2_bias_z
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

    return make_fragment_scan_exp(Exp)


LoadBackwardDipoleTrap = make_experiment(
    "LoadBackwardDipoleTrap",
    chamber_2_bias_x=0.29,
    chamber_2_bias_y=0.02,
    chamber_2_bias_z=-1.14,
    chamber_2_mot_current_start=3,
    chamber_2_mot_current_end=3,
    roi_0_x0=130,
    roi_0_x1=280,
    roi_0_y0=330,
    roi_0_y1=375,
)


LoadForwardDipoleTrap = make_experiment(
    "LoadForwardDipoleTrap",
    chamber_2_bias_x=0.4,
    chamber_2_bias_y=0.02,
    chamber_2_bias_z=-1.015,
    chamber_2_mot_current_start=3,
    chamber_2_mot_current_end=3,
    roi_0_x0=130,
    roi_0_x1=280,
    roi_0_y0=275,
    roi_0_y1=325,
)
