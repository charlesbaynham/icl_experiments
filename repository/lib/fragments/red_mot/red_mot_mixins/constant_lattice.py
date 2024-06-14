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


class _LatticeTurnerOnerer(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "lattice_setpoint",
            FloatParam,
            "SUServo setpoint for lattice at high power",
            default=constants.SUSERVOED_BEAMS["lattice_input_1379"].setpoint,
            unit="V",
        )
        self.lattice_setpoint: FloatParamHandle

        self.setattr_fragment(
            "lattice_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["lattice_input_1379"]]
            ),
        )
        self.lattice_setter: SetBeamsToDefaults

        self.first_run = True

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            self.first_run = False
            self.core.break_realtime()
            self.lattice_setter.turn_on_all()

        self.device_setup_subfragments()


class ConstantLatticeMixin(RedMOTWithExperiment):
    """
    Leaves lattice light on throughout the entire sequence.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * None
    """

    def build_fragment(self):
        super().build_fragment()

        # %% Fragments

        self.setattr_fragment("lattice_turneronner", _LatticeTurnerOnerer)
        self.lattice_turneronner: _LatticeTurnerOnerer

        self.setattr_param_rebind("lattice_setpoint", self.lattice_turneronner)
