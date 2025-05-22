import logging
from typing import List

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.experiment import delay_mu
from artiq.experiment import kernel
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
            ),
        )
        self.all_beam_default_setter: (
            SetBeamsToDefaults  # FIXME This is duplicated in dipole_trap_experiment
        )

        self.setattr_fragment(
            "hor_dipole_trap_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"]
                ],
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
                ],
                name="hor_dipole_trap_setter",
            ),
        )
        self.hor_dipole_trap_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "XODT_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
                    constants.SUSERVOED_BEAMS["down_813"],
                ],
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"],
                ],
                name="XODT_setter",
            ),
        )
        self.XODT_setter: SetBeamsToDefaults

        self.suservo_fragments: List[LibSetSUServoStatic] = []
        self.suservo_setpoint_offsets: List[float] = []

        # Make a SUServo controlling Fragment for each red beam, and store the
        # photodiode offsets for each
        for beam_info in DIPOLE_SUSERVO_INFOS:
            f = self.setattr_fragment(
                "suservofrag_" + beam_info.name,
                LibSetSUServoStatic,
                channel=beam_info.suservo_device,
            )
            self.suservo_fragments.append(f)
            self.suservo_setpoint_offsets.append(beam_info.photodiode_offset)

        # Make an array to store the nominal amplitudes but leave it empty for
        # now - we'll populate it in device_setup() so that we can scan over it
        self.suservo_nominal_amplitudes = [0.0] * len(DIPOLE_SUSERVO_INFOS)

        # %% DEVICES

        self.dipole_trap_1064_freespace_AOM: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"].urukul_device
        )
        self.kernel_invariants.add("dipole_trap_1064_freespace_AOM")

        # %% Kernel parameters

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)
        self.kernel_invariants.add("debug_mode")

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode"}

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Turn on dipole beams before blue MOT
        # self.core.break_realtime()
        # self.XODT_setter.turn_on_all()
        # delay_mu(int64(self.core.ref_multiplier))
        # self.core.break_realtime()
        # self.set_dipole_suservo_setpoints(
        #     setpoint_down_813=constants.XODT_MOLASSES_SETPOINT_MULTIPLES_START[5],
        #     setpoint_dipole_trap_1064_delivery=constants.XODT_MOLASSES_SETPOINT_MULTIPLES_START[
        #         4
        #     ],
        # )

        # Look up the SUServo setpoints from the default beam setter
        for i in range(len(self.suservo_nominal_amplitudes)):
            self.suservo_nominal_amplitudes[i] = (
                self.all_beam_default_setter.get_suservo_setpoint_by_index(i)
            )

        self.core.break_realtime()

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

    @kernel
    def set_dipole_suservo_setpoints(
        self,
        setpoint_down_813: TFloat = 1.0,
        setpoint_up_813: TFloat = 1.0,
        setpoint_dipole_trap_1064_delivery: TFloat = 1.0,
        setpoint_lattice_input_1379: TFloat = 1.0,
    ):
        """
        Set the SUServo target amplitudes of all dipole beams individually,
        expressed as a multiple of their nominal amplitudes
        """
        # Prepare array of beam amplitudes
        # This must match the ordering in DIPOLE_SUSERVO_INFOS
        setpoints = [
            setpoint_down_813,
            setpoint_up_813,
            setpoint_dipole_trap_1064_delivery,
            setpoint_lattice_input_1379,
        ]

        for i in range(len(self.suservo_fragments)):
            suservo_frag = self.suservo_fragments[i]
            nominal_setpoint = self.suservo_nominal_amplitudes[i]
            photodiode_offset = self.suservo_setpoint_offsets[i]

            setpoint = nominal_setpoint * setpoints[i] + photodiode_offset

            if self.debug_mode:
                logger.info(
                    "Setting %s setpoint to %.2f x %.2f + %.4f = %.3f V",
                    suservo_frag,
                    setpoints[i],
                    nominal_setpoint,
                    photodiode_offset,
                    setpoint,
                )

            suservo_frag.set_setpoint(setpoint)
