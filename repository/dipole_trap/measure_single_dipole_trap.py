import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixinBase,
)

logger = logging.getLogger(__name__)


class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImage,
    XODTSingleMolassesMixinBase,
):
    """
    Make Single XODT, image twice for BG subtraction
    """
    def build_fragment(self):
        super().build_fragment()   

        self.setattr_param_rebind(
            "delay_molasses",
            self.delay_before_molasses,
            original_name="delay_before_molasses",
            default= 0.01e-3,
        )    

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass    

class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    XODTSingleMolassesMixinBase,
):
    """
    Measure a single XODT with absorption imaging
    """
    def build_fragment(self):
        super().build_fragment()   

        self.setattr_param_rebind(
            "delay_molasses",
            self.delay_before_molasses,
            original_name="delay_before_molasses",
            default= 0.01e-3,
        )  

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

MeasureSingleXODTBGCorrectedFrag = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTAbsFrag = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
