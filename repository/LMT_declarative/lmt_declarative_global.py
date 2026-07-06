"""
Global-parameter LMT interferometry.

Like :mod:`repository.LMT.lmt_declarative`, but driven by the global-parameter
symmetric Mach-Zehnder mixin
(:class:`~repository.lib.experiment_templates.mixins.lmt_global_params.LMTGlobalParamsSymmetricMachZehnderMixin`)
instead of one parameter per pulse: the velocity selection, launch and
symmetric Mach-Zehnder interferometer are generated procedurally from a
compact set of global knobs (launch-pulse and LMT-recoil counts, per-beam
detunings and durations, delivery set points and dark times).
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    NormalisedFastKineticsLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTBase,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.lmt_global_params import (
    LMTGlobalParamsSymmetricMachZehnderMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)


class DeclarativeLMTGlobalSymmetricMachZehnderFrag(
    FLIRBlueMOTMeasurementMixin,
    LMTGlobalParamsSymmetricMachZehnderMixin,
    DeclarativeLMTBase,
    # See DeclarativeLMTSymmetricMachZehnderFrag: repositions the camera ROIs along the
    # predicted ballistic trajectory; do not also mix in a static-config imaging
    # mixin.
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Velocity selection, launch and Mach-Zehnder from global parameters.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_declarative_lmt()


DeclarativeLMTGlobalSymmetricMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTGlobalSymmetricMachZehnderFrag
)
