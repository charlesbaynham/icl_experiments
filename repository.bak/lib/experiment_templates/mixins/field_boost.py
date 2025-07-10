import logging

from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class FieldBoostMixin(RedMOTWithExperiment):
    """
    Mixin for :class:`~RedMOTWithExperiment` to boost the compensation fields at
    the start of the expansion time

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        for c in "xyz":
            self.setattr_param(
                f"{c}_coil_boost",
                FloatParam,
                default=0.0,
                description=f"Boost to {c} coil current",
                unit="A",
            )
        self.x_coil_boost: FloatParamHandle
        self.y_coil_boost: FloatParamHandle
        self.z_coil_boost: FloatParamHandle

    @kernel
    def field_boost(self):
        """
        Set fields to their "boosted" values

        This method does not advance the timeline but does require at least
        1.5us + 808ns * len(currents) on a Kasli 1.x as SPI events are written
        into the past.
        """
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.spectroscopy_field_gradient.get(),
            self.blue_3d_mot.chamber_2_bias_x.get() + self.x_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_y.get() + self.y_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_z.get() + self.z_coil_boost.get(),
        )

    @kernel
    def set_postnarrowband_fields_hook(self):
        """
        Override default setting to write compensation coils as well as the
        gradient coil
        """
        self.field_boost()
