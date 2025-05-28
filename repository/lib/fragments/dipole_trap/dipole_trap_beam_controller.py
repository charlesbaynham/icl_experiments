import logging

from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import Fragment
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

import repository.lib.constants as constants
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)

logger = logging.getLogger(__name__)

DIPOLE_SUSERVO_INFOS = [
    constants.SUSERVOED_BEAMS[beam]
    for beam in [
        "down_813",
        "dipole_trap_1064_delivery",
    ]
]
DIPOLE_URUKUL_INFOS = [
    constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
]


class DipoleBeamController(Fragment):
    """
    Methods for making and controlling the dipole trapping beams (including lattice beams).
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # Setup of defaults for all beams
        self.setattr_fragment(
            "all_beam_default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=DIPOLE_SUSERVO_INFOS,
                urukul_beam_infos=DIPOLE_URUKUL_INFOS,
                name="DipoleBeamSettings",
                use_automatic_setup=True,  # Automatically configure the DDSs but do not turn the beams on
                use_automatic_turnon=False,
            ),
        )
        self.all_beam_default_setter: SetBeamsToDefaults
        # FIXME This is duplicated in dipole_trap_experiment

        # Beam toggler - used for turning the beams on and off once the DDSs are
        # configured by the default setter
        self.setattr_fragment(
            "dipole_beam_toggler",
            make_toggle_list_of_beams(
                suservo_beam_infos=DIPOLE_SUSERVO_INFOS,
                urukul_beam_infos=DIPOLE_URUKUL_INFOS,
            ),
        )
        self.dipole_beam_toggler: ToggleListOfBeams

    @kernel
    def turn_off_dipole_beams(self):
        """
        Turns off all dipole beams

        Advances the timeline by a few coarse RTIO cycles
        """
        self.dipole_beam_toggler.turn_off_beams()

    @kernel
    def turn_on_dipole_beams(self):
        """
        Turns on all dipole beams

        Advances the timeline by a few coarse RTIO cycles
        """
        self.dipole_beam_toggler.turn_on_beams()
