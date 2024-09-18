from ndscan.experiment import *

from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)


class ExponentialDecayMixin(SingleAndorImage):
    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "exponential_decay",
                data={
                    "x": self.expansion_time,
                    "y": self.andor_mean,
                },
            )
        ]
