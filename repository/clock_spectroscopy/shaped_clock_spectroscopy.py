import logging

from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from numpy import int64

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
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDownBeamDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class ShapedClockSpecWithSlicingFrag(
    # Clock spec:
    ShapedRabiSpectroscopyDipoleTrapMixin,
    # Velocity slicing:
    ClockShelvingAndClearoutDipoleTrapMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Imaging:
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadSingleXODTWithPainterMixin,
    # Cooling
    XODTSingleMolassesPlusDipoleRampMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    # Base:
    DipoleTrapWithExperimentBase,
):
    """
    Shaped clock spectroscopy from dropped, velocity-sliced single XODT

    Load into an XODT, drop the atoms, state-prepare, velocity-slice (unshaped)
    then use the up clock beam for spectroscopy, altering the (single-pass)
    SUServo AOM's frequency and shaping the pulse with the final switch AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def post_dipole_trap_hook(self):
        self.post_dipole_trap_hook_shaped_pulses()
        delay_mu(int64(self.core.ref_multiplier))
        self.post_dipole_trap_hook_default()
        self.post_dipole_trap_hook_shelving_and_clearout()


class ClockSpecDownFromSingleXODTEvaporatedShapedSlicingFrag(
    ClockRabiSpectroscopyDownBeamDipoleTrapMixin,
    # Imaging
    NormalisedDipoleTrapFastKineticsMixin,  # defines ROI
    NormalisedFastKineticsRepumpedMixin,  # turns on repumps
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadSingleXODTWithPainterMixin,
    # Cooling
    XODTSingleMolassesPlusDipoleRampMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    # State prep
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    # Slicing
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Down beam clock spectroscopy from dropped single XODT with evaporation, shaped shelving and clearout

    Load into an XODT, velocity-slice using a shaped pulse, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def post_sequence_cleanup_checkpoint(self):
        # andor / shelving / loading cleanups now cascade automatically via
        # post_sequence_cleanup_checkpoint_subfragments(). This override is
        # retained only for the experiment-specific shaped-pulse re-prep.
        self.post_sequence_cleanup_checkpoint_subfragments()
        self.post_sequence_cleanup_checkpoint_base()
        self.post_dipole_trap_hook_shaped_pulses()


class ClockSpecFromSingleXODTEvaporatedShapedSlicingFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    # Imaging
    NormalisedDipoleTrapFastKineticsMixin,  # defines ROI
    NormalisedFastKineticsRepumpedMixin,  # turns on repumps
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadSingleXODTWithPainterMixin,
    # Cooling
    XODTSingleMolassesPlusDipoleRampMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    FieldOnlyRampInEvapMixin,
    # State prep
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    # Slicing
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Clock spectroscopy from dropped single XODT with evaporation, shaped shelving and clearout

    Load into an XODT, velocity-slice using a shaped pulse, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def post_sequence_cleanup_checkpoint(self):
        # andor / shelving / loading cleanups now cascade automatically via
        # post_sequence_cleanup_checkpoint_subfragments(). This override is
        # retained only for the experiment-specific shaped-pulse re-prep.
        self.post_sequence_cleanup_checkpoint_subfragments()
        self.post_sequence_cleanup_checkpoint_base()
        self.post_dipole_trap_hook_shaped_pulses()


ShapedClockSpecWithSlicing = make_fragment_scan_exp(
    ShapedClockSpecWithSlicingFrag, max_rtio_underflow_retries=0
)

ClockSpecFromSingleXODTEvaporatedShapedSlicing = make_fragment_scan_exp(
    ClockSpecFromSingleXODTEvaporatedShapedSlicingFrag
)
ClockSpecDownFromSingleXODTEvaporatedShapedSlicing = make_fragment_scan_exp(
    ClockSpecDownFromSingleXODTEvaporatedShapedSlicingFrag
)
