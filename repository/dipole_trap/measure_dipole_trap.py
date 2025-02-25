import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

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

logger = logging.getLogger(__name__)


class _MeasureSingleXODTFrag(ConstantBeamsMixin, DipoleTrapWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_experiment", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    # @kernel
    # def do_experiment_after_red_mot_hook(self):
    #     # turn off dipole trap beams to expand cloud. override the hook to not have all the stages after dipole trap
    #     self.constant_dipole_traps_setter.set_all_beams_off() 
    #     pass

class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImage,
    _MeasureSingleXODTFrag,
):
    """
    Make Single XODT, image twice for BG subtraction
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass    

class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    _MeasureSingleXODTFrag,
):
    """
    Measure a single XODT, no molasses, with absorption imaging
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

MeasureSingleXODTBGCorrectedFrag = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTAbsFrag = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
