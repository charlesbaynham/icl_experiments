import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import Fragment
from numpy import int64
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]
logger = logging.getLogger(__name__)


class ClockShelvingAndClearoutBase(RedMOTWithExperiment):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "shelving_pulse_time",
            FloatParam,
            "Length of clock shelving pulse",
            default=constants.CLOCK_SHELVING_PULSE_TIME,
            unit="us",
        )
        self.shelving_pulse_time: FloatParamHandle

        self.setattr_param(
            "shelving_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during clock shelving pulse",
            default=0,
            unit="kHz",
        )
        self.shelving_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "shelving_pulse_clearout_duration",
            FloatParam,
            "Duration of 461 clearout pulse after shelving",
            default=constants.SHELVING_PULSE_CLEAROUT_DURATION,
            unit="us",
        )
        self.shelving_pulse_clearout_duration: FloatParamHandle

        self.setattr_param(
            "clock_delivery_preempt_time_shelving",
            FloatParam,
            "Preempt time before shelving pulse",
            default=constants.CLOCK_DELIVERY_PREEMPT_TIME,
            unit="us",
        )
        self.clock_delivery_preempt_time_shelving: FloatParamHandle

        self.setattr_param(
            "shelving_clock_delivery_setpoint",
            FloatParam,
            "Setpoint for clock delivery AOM during shelving",
            default=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            min=0.0,
            unit="V",
        )
        self.shelving_clock_delivery_setpoint: FloatParamHandle

        if not hasattr(self, "clock_delivery_setter"):
            self.setattr_fragment(
                "clock_delivery_setter",
                LibSetSUServoStatic,
                channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
            )
        self.clock_delivery_setter: LibSetSUServoStatic

        self.clock_dds: AD9910 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure the clock beam is set up
        # %% Fragments
        if not hasattr(self, "clock_default_setter"):
            # Create the default setter for the clock beam
            # if it has not already been created
            self.setattr_fragment(
                "clock_default_setter",
                make_set_beams_to_default(
                    suservo_beam_infos=[
                        CLOCK_BEAM_DELIVERY_INFO,
                    ],
                    urukul_beam_infos=[
                        CLOCK_BEAM_INFO,
                    ],
                    use_automatic_setup=True,
                    use_automatic_turnon=False,
                ),
            )
            self.clock_default_setter: SetBeamsToDefaults

            self.clock_delivery_handles = (
                self.clock_default_setter.get_setpoints_beaminfo_setters()[
                    CLOCK_BEAM_DELIVERY_INFO.name
                ][1]
            )
            self.kernel_invariants.add("clock_delivery_handles")

        # Kernel variable to record the moment of the velocity slicing pulse so
        # that other pulses can be relative to it
        self.t_velocity_slicing_pulse_centre_mu = int64(0)

        # Ensure that the time of the slicing pulse is always reset
        class _ResetSlicingTime(Fragment):
            def build_fragment(self, ref_to_outer_self):
                self.outer = ref_to_outer_self

    def get_always_shown_params(self):
        # Expose the clock base frequency for convenience
        param_handles = super().get_always_shown_params()
        if self.clock_delivery_handles.frequency_handle not in param_handles:
            param_handles.append(self.clock_delivery_handles.frequency_handle)
        return param_handles

    @kernel
    def clock_shelving(self):
        # Prepare the clock beam
        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time_shelving.get())
        self.clock_delivery_setter.set_suservo(
            freq=self.clock_delivery_handles.frequency_handle.get()
            + self.shelving_pulse_aom_detuning.get(),
            amplitude=self.clock_delivery_handles.initial_amplitude_handle.get(),
            attenuation=CLOCK_BEAM_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.shelving_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        at_mu(_t_start)

        # Record the time of the centre of the shelving pulse
        self.t_velocity_slicing_pulse_centre_mu = _t_start + self.core.seconds_to_mu(
            self.shelving_pulse_time.get()
        )

        # Pulse it onto the atoms
        self.fire_clock_shelving_pulse()

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.shelving_pulse_clearout_duration.get(),
            ignore_final_shutters=True,
        )

    @kernel
    def fire_clock_shelving_pulse(self):
        """
        Fire the clock shelving pulse onto the atoms.
        """
        self.clock_dds.sw.on()
        delay(self.shelving_pulse_time.get())
        self.clock_dds.sw.off()


class ClockShelvingAndClearoutRedMOTMixin(ClockShelvingAndClearoutBase):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_shelving()


class ClockShelvingAndClearoutDipoleTrapMixin(
    ClockShelvingAndClearoutBase, DipoleTrapWithExperiment
):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_dipole_trap_hook`
    """

    @kernel
    def post_dipole_trap_hook(self):
        self.post_dipole_trap_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.post_dipole_trap_hook_shelving_and_clearout()

    @kernel
    def post_dipole_trap_hook_shelving_and_clearout(self):
        """
        Before spectroscopy in the dipole trap but after dropping, fire a
        velocity-selection pulse
        """
        self.clock_shelving()
