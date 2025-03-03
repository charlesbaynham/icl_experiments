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
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    LoadSingleXODTMixin,
)

logger = logging.getLogger(__name__)


class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImage,
    LoadSingleXODTMixin,
):
    """
    Make Single XODT, image twice for BG subtraction
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass    

class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    LoadSingleXODTMixin,
):
    """
    Measure a single XODT with absorption imaging
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

MeasureSingleXODTBGCorrectedFrag = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTAbsFrag = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
