import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)

from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecFromXXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped XXODT

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()


class ClockSpecFromXXODTWithShelvingAndClearoutFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped XXODT with shelving and clearout

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()


ClockSpecFromXXODT = make_fragment_scan_exp(ClockSpecFromXXODTFrag)
ClockSpecFromXXODTWithShelving = make_fragment_scan_exp(
    ClockSpecFromXXODTWithShelvingAndClearoutFrag
)
