import logging

from repository.lib import constants

logger = logging.getLogger(__name__)

SWAP_BEAMS_INFO = {
    "red_up": constants.SUSERVOED_BEAMS["red_up"],
    "down_689": constants.SUSERVOED_BEAMS["down_689"],
}


# This is commented out because it deterministically won't work until the TODOs
# in it are fixed. If you want to use it, fix them.

# class DipoleSWAPMixin(DipoleTrapWithExperiment):
#     """
#     Mixin for implementing SWAP in the dipole trap.

#     Kernel hooks used (multiple mixins cannot use the same hooks):

#     * :meth:`~post_dipole_trap_hook`
#     """

#     def build_fragment(self):
#         super().build_fragment()
#         ### Fragments ###

#         # Setup the default DDS settings for the 689 down delivery AOM
#         self.setattr_fragment(
#             "set_default_down_689_delivery",
#             make_set_beams_to_default(
#                 suservo_beam_infos=[constants.SUSERVOED_BEAMS["down_689"]],
#                 name="down_689_default_setter",
#                 use_automatic_setup=True,
#             ),
#         )
#         self.set_default_down_689_delivery: SetBeamsToDefaults

#         self.setattr_fragment(
#             "down_689_setter",
#             LibSetSUServoStatic,
#             "suservo_aom_singlepass_689_down_beam",
#         )
#         self.down_689_setter: LibSetSUServoStatic

#         self.setattr_fragment(
#             "up_689_setter",
#             LibSetSUServoStatic,
#             "suservo_aom_singlepass_689_up",
#         )
#         self.up_689_setter: LibSetSUServoStatic

#         self.setattr_fragment(
#             "up_swap_beam_toggler",
#             ControlBeamsWithoutCoolingAOM,
#             beam_infos=[constants.SUSERVOED_BEAMS["red_up"]],
#         )
#         self.up_swap_beam_toggler: ControlBeamsWithoutCoolingAOM

#         self.setattr_device("ttl_shutter_red_up")
#         self.ttl_shutter_red_up: TTLOut

#         ### Parameters ###

#         self.setattr_param(
#             "swap_pulse_duration",
#             FloatParam,
#             "Duration of dipole trap swap pulse",
#             default=100e-6,
#             unit="us",
#         )
#         self.swap_pulse_duration: FloatParamHandle

#         self.setattr_param(
#             "ramp_frequency_dipole_swap",
#             FloatParam,
#             "689 injection AOM ramp frequency for dipole trap SWAP",
#             unit="kHz",
#             default=constants.RED_INJECTION_AOM_RAMP_FREQUENCY,
#         )
#         self.ramp_frequency_dipole_swap: FloatParamHandle

#         self.setattr_param(
#             "ramp_lower_detuning",
#             FloatParam,
#             "689 ramp upper-limit detuning from nominal frequency for dipole trap SWAP",
#             unit="MHz",
#             default=0.0,
#         )
#         self.ramp_lower_detuning: FloatParamHandle

#         self.setattr_param(
#             "ramp_upper_detuning",
#             FloatParam,
#             "689 ramp upper-limit detuning from nominal frequency for dipole trap SWAP",
#             unit="MHz",
#             default=constants.RED_BROADBAND_RAMP_UPPER_LIMIT,
#         )
#         self.ramp_upper_detuning: FloatParamHandle

#         self.setattr_param(
#             "swap_setpoint_up",
#             FloatParam,
#             "Setpoint of the 689 up beam during dipole trap SWAP",
#             default=0.0,
#             unit="V",
#         )
#         self.swap_setpoint_up: FloatParamHandle

#         self.setattr_param(
#             "swap_setpoint_down",
#             FloatParam,
#             "Setpoint of the 689 down beam during dipole trap SWAP",
#             default=0.0,
#             unit="V",
#         )
#         self.swap_setpoint_down: FloatParamHandle

#         self.setattr_param(
#             "hold_duration_after_swap",
#             FloatParam,
#             "Time to hold after the SWAP pulse",
#             default=10e-3,
#             unit="ms",
#         )
#         self.hold_duration_after_swap: FloatParamHandle

#         # For now, bind both setpoints together
#         # TODO: balance these beams and
#         # allow ramping independently / together based on Rabi frequency
#         # measurements in 2024-11-29 labbook entry
#         self.setattr_param_like("joint_swap_setpoint", self, "swap_setpoint_up")
#         self.bind_param("swap_setpoint_up", self.joint_swap_setpoint)
#         self.bind_param("swap_setpoint_down", self.joint_swap_setpoint)

#     @kernel
#     def start_ramping_red_for_dipole_swap(self):
#         """
#         Start modulation of the 689 DDS as configured

#         Advances the timeline by the duration of SPI writes
#         """

#         ramp_rate_dipole_swap = abs(
#             (self.ramp_lower_detuning.get() - self.ramp_upper_detuning.get())
#             * self.ramp_frequency_dipole_swap.get()
#         )

#         self.red_mot.red_beam_controller.injection_aom_ramper.start_ramp(
#             ramp_rate_dipole_swap,
#             self.red_mot.injection_aom_static_frequency.get()
#             + self.ramp_lower_detuning.get(),
#             self.red_mot.injection_aom_static_frequency.get()
#             + self.ramp_upper_detuning.get(),
#             wave_type=2,  # The red AOM is negatively double passed, so this is a ramp from more negative to more positive frequency
#         )

#     @kernel
#     def do_dipole_swap_pulse(self):
#         """
#         Do a Stark shifting pulse for the duration specified by `stark_pulse_duration`.

#         Advances the timeline by `stark_pulse_duration` + some SPI writes.
#         """
#         if self.swap_pulse_duration.get() == 0.0:
#             return

#         self.start_ramping_red_for_dipole_swap()

#         self.ttl_shutter_red_up.on()
#         delay_mu(int64(self.core.ref_multiplier))
#         # Start the SWAP beams at zero power so we won't get a flash of bright
#         # light

#         # TODO: this is half hacked and doesn't make sense, but we're not
#         # going to use SWAP for now. If SWAP is reattempted later this MUST be
#         # fixed otherwise it definitely won't work
#         self.down_689_setter.suservo_channel.set_y(
#             self.down_689_setter.suservo_profile, 0.13 * self.swap_setpoint_down.get()
#         )
#         delay_mu(int64(self.core.ref_multiplier))
#         self.up_689_setter.suservo_channel.set_y(
#             self.up_689_setter.suservo_profile, 0.01 * self.swap_setpoint_down.get()
#         )
#         delay_mu(int64(self.core.ref_multiplier))
#         # Long delay for up beam shutter to open
#         delay(20e-3)

#         # Write setpoints for the SWAP beams

#         # TODO: this currently overwrites the setpoints in beam_info. Get rid of one of them
#         # TODO: Probably we would rather use the setpoints than just set amplitude (though not for sure)
#         # self.down_689_setter.set_setpoint(self.swap_setpoint_down.get())
#         # delay_mu(int64(self.core.ref_multiplier))
#         # self.up_689_setter.set_setpoint(self.swap_setpoint_up.get())
#         # delay_mu(int64(self.core.ref_multiplier))

#         self.up_689_setter.set_channel_state(rf_switch_state=True, enable_iir=False)
#         delay_mu(int64(self.core.ref_multiplier))
#         self.down_689_setter.set_channel_state(rf_switch_state=True, enable_iir=False)
#         delay(self.swap_pulse_duration.get())
#         self.down_689_setter.set_channel_state(rf_switch_state=False, enable_iir=False)
#         self.up_swap_beam_toggler.turn_beams_off()

#     @kernel
#     def post_dipole_trap_hook(self):
#         """
#         At the end of the dipole trap, right before spectroscopy etc, do a SWAP
#         pulse before turning off the trap beams
#         """
#         self.do_dipole_swap_pulse()

#         delay(self.hold_duration_after_swap.get())

#         # Turns off the dipole trap beams
#         self.post_dipole_trap_hook_default()
