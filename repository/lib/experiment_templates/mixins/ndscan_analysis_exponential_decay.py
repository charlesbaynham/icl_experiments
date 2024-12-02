from ndscan.experiment import *

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment


def make_exponential_decay_mixin(x_axis_param: str):
    class ExponentialDecayMixin(RedMOTWithExperiment):
        def get_default_analyses(self):
            super_analysis = super().get_default_analyses()

            # Valid output channels for exponential decay:
            possible_channels = [
                "andor_mean",
                "andor_mean_bg_corrected",
                "andor_sum",
                "image_horizontal_mean",
                "image_vertical_mean",
                "excitation_fraction",
                "excitation_fraction_forward",
                "excitation_fraction_backward",
            ]

            # Filter by whether they exist or not for this fragment
            valid_channels = [c for c in possible_channels if hasattr(self, c)]

            return super_analysis + [
                OnlineFit(
                    "exponential_decay",
                    data={"x": getattr(self, x_axis_param), "y": getattr(self, c)},
                )
                for c in valid_channels
            ]

    return ExponentialDecayMixin


ExponentialDecayMixin = make_exponential_decay_mixin("expansion_time")
