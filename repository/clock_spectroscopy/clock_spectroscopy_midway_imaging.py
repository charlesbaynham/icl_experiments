import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.midway_imaging import (
    MidSequenceAndorImageMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecMidwayImagingFrag(
    MidSequenceAndorImageMixin,
    EMGainMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Midway imaging of clock sequence

    Load into an XXODT, spin-polarize the atoms then velocity slice them, as if
    for a clock interferometry / spec experiment.

    But, image midway through the sequence instead, with the imaging time
    measured relative to the start of the BB red MOT.

    Finally, take a background image at the end of the sequence.
    """


ClockSpecMidwayImaging = make_fragment_scan_exp(ClockSpecMidwayImagingFrag)
