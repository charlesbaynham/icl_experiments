from repository.lib.experiment_templates.mixins.field_boost import FieldBoostMixin
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
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrap,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)

logger = logging.getLogger(__name__)


class RedSpectroscopyFromXXODTFrag(
    RedSpectroscopyDipoleTrap,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    FieldBoostMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    689 spectroscopy from dropped XXODT

    Load into an XXODT, then use the up beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_red_spectroscopy()
        self.post_narrowband_hook_xodt_molasses()
        self.post_narrowband_hook_default()


RedSpectroscopyFromXXODT = make_fragment_scan_exp(RedSpectroscopyFromXXODTFrag)
