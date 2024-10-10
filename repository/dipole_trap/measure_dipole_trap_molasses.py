import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import XODTMolassesMixin

logger = logging.getLogger(__name__)

EXPOSE_MOLASSES_1_PARAMS = True
EXPOSE_MOLASSES_2_PARAMS = True


class _MeasureDipoleTrapFrag(XODTMolassesMixin):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("spectroscopy_field_gradient", 0)

        # Expose the molasses ramp parameters if desired
        if EXPOSE_MOLASSES_1_PARAMS:
            names = [_ for _ in self.molasses_xodt_1._free_params.keys()]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_1_{name}", self.molasses_xodt_1, original_name=name
                )
        if EXPOSE_MOLASSES_2_PARAMS:
            names = [_ for _ in self.molasses_xodt_2._free_params.keys()]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_2_{name}", self.molasses_xodt_2, original_name=name
                )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Release the atoms for time of flight measurement
        self.dipole_beam_controller.turn_off_dipole_beams()


class MeasureDipoleTrapFrag(
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    SingleAndorImage,
    _MeasureDipoleTrapFrag,
):
    """
    Load a dipole trap, implement 689 molasses, release, and image with the ANDOR
    """


MeasureDipoleTrap = make_fragment_scan_exp(MeasureDipoleTrapFrag)
