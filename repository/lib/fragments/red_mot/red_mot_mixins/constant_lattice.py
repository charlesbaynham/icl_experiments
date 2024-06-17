import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


def make_beam_turneronner(beam_name):
    class TurnerOnerer(Fragment):
        def build_fragment(self):
            self.setattr_device("core")
            self.core: Core

            self.setattr_param(
                "setpoint",
                FloatParam,
                "SUServo setpoint",
                default=constants.SUSERVOED_BEAMS[beam_name].setpoint,
                unit="V",
            )
            self.setpoint: FloatParamHandle

            self.setattr_fragment(
                "setter",
                make_set_beams_to_default(
                    suservo_beam_infos=[constants.SUSERVOED_BEAMS[beam_name]]
                ),
            )
            self.setter: SetBeamsToDefaults

            self.first_run = True

        @kernel
        def device_setup(self) -> None:
            if self.first_run:
                self.first_run = False
                self.core.break_realtime()
                self.setter.turn_on_all()

            self.device_setup_subfragments()

    return TurnerOnerer


class ConstantLatticeMixin(RedMOTWithExperiment):
    """
    Leaves lattice light (cavity & 813) on throughout the entire sequence.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * None
    """

    def build_fragment(self):
        super().build_fragment()

        # %% Fragments

        self.setattr_fragment(
            "lattice_1379_turneronner", make_beam_turneronner("lattice_input_1379")
        )
        self.setattr_fragment("beam_813_turneronner", make_beam_turneronner("up_813"))

        self.setattr_param_rebind(
            "setpoint_1379",
            self.lattice_1379_turneronner,
            original_name="setpoint",
        )
        self.setattr_param_rebind(
            "setpoint_813", self.beam_813_turneronner, original_name="setpoint"
        )
