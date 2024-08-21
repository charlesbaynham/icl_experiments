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
            "constant_dipole_traps_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["lattice_input_1379"],
                    constants.SUSERVOED_BEAMS["down_813"],
                    constants.SUSERVOED_BEAMS["up_813"],
                    constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
                ],
                urukul_beam_infos=[constants.URUKULED_BEAMS["dipole_trap_1064_switch"]],
                use_automatic_setup=True,
            ),
        )
        self.constant_dipole_traps_setter: SetBeamsToDefaults
