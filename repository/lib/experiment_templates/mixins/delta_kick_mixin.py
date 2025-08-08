from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)

class DeltaKickCoolingMixin(DipoleTrapWithExperiment):
    """
    Turns off the dipole beams and turns on the delta-kick cooling beams

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~delta_kick_cooling_hook`
    """

    def build_fragment(self):
        super().build_fragment()
