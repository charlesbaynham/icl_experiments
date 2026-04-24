from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForLMTMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTRetroedMolassesPlusDipoleRampMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)


class LaunchFromXODTFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    # XODTRetroedMolassesPlusDipoleRampMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    Launch from XODT

    Load into an XODT, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_loading()
        self.post_sequence_cleanup_hook_shelving()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class DoubleLaunchFromXODTFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    Double launch from XODT

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class LaunchFromXODTShapedShelvingFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    Launch from XODT with shaped shelving

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


LaunchFromXODT = make_fragment_scan_exp(
    LaunchFromXODTFrag, max_rtio_underflow_retries=0
)

DoubleLaunchFromXODT = make_fragment_scan_exp(
    DoubleLaunchFromXODTFrag, max_rtio_underflow_retries=0
)

LaunchFromXODTShapedShelving = make_fragment_scan_exp(
    LaunchFromXODTShapedShelvingFrag, max_rtio_underflow_retries=0
)
