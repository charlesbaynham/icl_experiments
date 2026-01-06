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
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForLMTMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTLaunchDoubleTrapMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    ShapedFirstPulseLMTInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)


class LMTInterferometryFrag(
    LMTInterferometryMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    LMT interferometry without launch

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


class LMTInterferometryWithDoubleLaunchFrag(
    LMTInterferometryMixin,
    LMTLaunchDoubleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    LMT interferometry with double trap launch

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


class LMTInterferometryWithLaunchFrag(
    LMTInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    LMT interferometry with launch

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


class ShapedFirstPulseLMTInterferometryFrag(
    ShapedFirstPulseLMTInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    LMT interferometry with shaped selective pulses

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


LMTInterferometryExp = make_fragment_scan_exp(
    LMTInterferometryFrag, max_rtio_underflow_retries=0
)
LMTInterferometryWithLaunch = make_fragment_scan_exp(LMTInterferometryWithLaunchFrag)
ShapedFirstPulseLMTInterferometry = make_fragment_scan_exp(
    ShapedFirstPulseLMTInterferometryFrag
)
LMTInterferometryWithDoubleLaunch = make_fragment_scan_exp(
    LMTInterferometryWithDoubleLaunchFrag
)
