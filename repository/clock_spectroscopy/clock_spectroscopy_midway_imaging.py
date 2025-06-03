import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.midway_imaging import (
    MidSequenceAndorImage,
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
    MidSequenceAndorImage,
    EMGain,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Midway imaging of clock sequence

    Load into an XXODT, spin-polarize the atoms then velocity slice them, as if
    for a clock interferometry / spec experiment.

    But, image midway through the sequence instead, with the imaging time
    measured relative to the start of the BB red MOT.

    Finally, take a background image at the end of the sequence.
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockshelving()

    @kernel
    def start_of_red_broadband_hook(self):
        self.start_of_red_broadband_hook_imaging_base()
        self.start_of_red_broadband_hook_midway_imaging()


ClockSpecMidwayImaging = make_fragment_scan_exp(ClockSpecMidwayImagingFrag)
