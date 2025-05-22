import logging

from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from numpy import int64

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    FieldOnlyRampInEvapMixin,
)

logger = logging.getLogger(__name__)


class ShapedClockSpecFromSingleXODTFrag(
    # Clock spec:
    ShapedRabiSpectroscopyDipoleTrapMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Imaging:
    NormalisedDipoleTrapFastKineticsMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadSingleXODTMixin,
    # Base:
    DipoleTrapWithExperiment,
):
    """
    Shaped clock spectroscopy from dropped single XODT

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) SUServo AOM's frequency and shaping the pulse with the final
    switch AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()


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
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadSingleXODTMixin,
    # Base:
    DipoleTrapWithExperiment,
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
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()

    @kernel
    def post_dipole_trap_hook(self):
        self.post_dipole_trap_hook_shaped_pulses()
        delay_mu(int64(self.core.ref_multiplier))
        self.post_dipole_trap_hook_default()
        self.post_dipole_trap_hook_shelving_and_clearout()


ShapedClockSpecFromSingleXODT = make_fragment_scan_exp(
    ShapedClockSpecFromSingleXODTFrag, max_rtio_underflow_retries=0
)

ShapedClockSpecWithSlicing = make_fragment_scan_exp(
    ShapedClockSpecWithSlicingFrag, max_rtio_underflow_retries=0
)
