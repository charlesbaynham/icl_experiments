import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTMolassesPlusFieldRampMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)

logger = logging.getLogger(__name__)


class ClockSpecFromXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    TripleImageDipoleTrapFastKineticsMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTMolassesPlusFieldRampMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped XODT

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """


ClockSpecFromXODT = make_fragment_scan_exp(ClockSpecFromXODTFrag)
