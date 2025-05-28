import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment import Fragment
from numpy import int64
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants

logger = logging.getLogger(__name__)

DIPOLE_SUSERVO_INFOS = [
    constants.SUSERVOED_BEAMS[beam]
    for beam in [
        "down_813",
        "up_813",
        "dipole_trap_1064_delivery",
        "lattice_input_1379",
    ]
]


class DipoleBeamController(Fragment):
    """
    Methods for making and controlling the dipole trapping beams (including lattice beams).
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # %% FRAGMENTS

        # Setup of defaults for all beams
        self.setattr_fragment(
            "all_beam_default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=DIPOLE_SUSERVO_INFOS,
                name="DipoleBeamSettings",
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
                ],
                use_automatic_setup=True,
                use_automatic_turnon=False,
            ),
        )
        self.all_beam_default_setter: (
            SetBeamsToDefaults  # FIXME This is duplicated in dipole_trap_experiment
        )

        # FIXME: unused
        # self.setattr_fragment(
        #     "hor_dipole_trap_setter",
        #     make_set_beams_to_default(
        #         suservo_beam_infos=[
        #             constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"]
        #         ],
        #         urukul_beam_infos=[
        #             constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
        #         ],
        #         name="hor_dipole_trap_setter",
        #     ),
        # )
        # self.hor_dipole_trap_setter: SetBeamsToDefaults

        # self.setattr_fragment(
        #     "XODT_setter",
        #     make_set_beams_to_default(
        #         suservo_beam_infos=[
        #             constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
        #             constants.SUSERVOED_BEAMS["down_813"],
        #         ],
        #         urukul_beam_infos=[
        #             constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
        #         ],
        #         name="XODT_setter",
        #     ),
        # )
        # self.XODT_setter: SetBeamsToDefaults

        self.suservo_fragments: List[LibSetSUServoStatic] = []

        # Make a SUServo controlling Fragment for each beam
        for beam_info in DIPOLE_SUSERVO_INFOS:
            f = self.setattr_fragment(
                "suservofrag_" + beam_info.name,
                LibSetSUServoStatic,
                channel=beam_info.suservo_device,
            )
            self.suservo_fragments.append(f)

    @kernel
    def turn_off_dipole_beams(self):
        """
        Turns off all dipole beams

        Advances the timeline by a few coarse RTIO cycles
        """

        for i in range(len(self.suservo_fragments)):
            self.suservo_fragments[i].set_channel_state(
                rf_switch_state=False, enable_iir=False
            )
            delay_mu(int64(self.core.ref_multiplier))
