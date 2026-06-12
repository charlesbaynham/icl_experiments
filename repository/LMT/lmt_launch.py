from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
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
    XODTSingleMolassesPlusDipoleRampMixin,
)


class LaunchFromXODTFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    # XODTRetroedMolassesPlusDipoleRampMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Launch from XODT

    Load into an XODT, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class DoubleLaunchFromXODTFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Double launch from XODT

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class LaunchFromXODTShapedShelvingFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Launch from XODT with shaped shelving

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

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
