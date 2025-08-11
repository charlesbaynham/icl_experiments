import logging

from artiq.coredevice.ad9910 import AD9910
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
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import UrukuledBeam


CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]


class DeltaKickCoolingMixin(DipoleTrapWithExperiment):
    """
    Turns off the dipole beams and turns on the delta-kick cooling beams

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~delta_kick_cooling_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "up_813_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["up_813"].suservo_device,
        )
        self.up_813_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "up_813_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["up_813"]]
            ),
        )
        self.up_813_setter: SetBeamsToDefaults

        self.setattr_param(
        "up_813_duration",
            FloatParam,
        "Time to spend in the up beam",
        default = 3e-3,
        unit= "ms"
        )

    @kernel
    def delta_kick_cooling_hook(self):

        self.up_813_setter.turn_on_all()

        self.up_813_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )
