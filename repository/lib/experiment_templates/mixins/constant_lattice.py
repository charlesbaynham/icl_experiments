import logging

from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)

logger = logging.getLogger(__name__)


class ConstantBeamsMixin(RedMOTWithExperimentBase):
    """
    Leaves a list of SUServo beams on throughout the entire sequence.

    Current list:
    * squeezing_cavity_698

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
                    # constants.SUSERVOED_BEAMS["down_813"],
                    # constants.SUSERVOED_BEAMS["up_813"],
                    # constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
                    # constants.SUSERVOED_BEAMS["dipole_trap_painted_1064_delivery"],
                    # constants.SUSERVOED_BEAMS["clock_delivery"],
                    # constants.SUSERVOED_BEAMS["stark_shifter_689_delivery"],
                    constants.SUSERVOED_BEAMS["squeezing_cavity_698"],
                ],
                urukul_beam_infos=[
                    # constants.URUKULED_BEAMS["clock_up"],
                ],
                use_automatic_setup=True,
                use_automatic_turnon=True,
            ),
        )
        self.constant_dipole_traps_setter: SetBeamsToDefaults
