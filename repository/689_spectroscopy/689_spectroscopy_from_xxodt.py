import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingRepumpedNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.red_spectroscopy import (
    RedSpectroscopyDipoleTrap,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadXXODTMixin

logger = logging.getLogger(__name__)


class RedSpectroscopyFromXXODTFrag(
    RedSpectroscopyDipoleTrap,
    DoubleTrapImagingRepumpedNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadXXODTMixin,
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


RedSpectroscopyFromXXODT = make_fragment_scan_exp(RedSpectroscopyFromXXODTFrag)
