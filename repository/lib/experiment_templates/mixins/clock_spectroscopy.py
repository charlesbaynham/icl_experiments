import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]


logger = logging.getLogger(__name__)


class ClockSpectroscopyBase(ExponentialDecayMixin, RedMOTWithExperimentBase):
    """
    Sets up the clock beam for clock spectroscopy (including clock shelving or interferometry)

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of delivery AOM during spectroscopy pulse",
            default=constants.CLOCK_DELIVERY_SPECTROSCOPY_DETUNING,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "spectroscopy_clock_delivery_setpoint",
            FloatParam,
            "Setpoint for clock delivery AOM",
            default=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            min=0.0,
            unit="V",
        )
        self.spectroscopy_clock_delivery_setpoint: FloatParamHandle

        self.setattr_param(
            "clock_delivery_preempt_time",
            FloatParam,
            "Preempt time before spectroscopy pulse",
            default=constants.CLOCK_DELIVERY_PREEMPT_TIME,
            unit="us",
        )
        self.clock_delivery_preempt_time: FloatParamHandle

        if not hasattr(self, "clock_delivery_setter"):
            self.setattr_fragment(
                "clock_delivery_setter",
                LibSetSUServoStatic,
                channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
            )
        self.clock_delivery_setter: LibSetSUServoStatic

        self.clock_up_dds: AD9910 = self.get_device(CLOCK_UP_BEAM_INFO.urukul_device)
        self.clock_down_dds: AD9910 = self.get_device(
            CLOCK_DOWN_BEAM_INFO.urukul_device
        )

        # Set nominal DDS frequencies so the pulse recorder has correct defaults
        # even for experiments that never explicitly call clock_up/down_dds.set()
        # (e.g. simple Rabi spectroscopy where the DDS is configured only in
        # device_setup, not immediately before each pulse).
        self._tracked_up_dds_freq = CLOCK_UP_BEAM_INFO.frequency
        self._tracked_down_dds_freq = CLOCK_DOWN_BEAM_INFO.frequency

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

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
                        CLOCK_UP_BEAM_INFO,
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

        # Bind the default setter's setpoint to this fragment's parameters, for
        # ease of use
        self.clock_default_setter.bind_param(
            self.clock_delivery_handles.setpoint_handle.name,
            self.spectroscopy_clock_delivery_setpoint,
        )

        # Turn the clock delivery AOM on at the start of each shot. This might
        # get overridden by e.g. slicing so we must do it again, but we want the
        # duty cycle to be 100% so the AOM settles
        class TurnOnClockDeliveryAOM(Fragment):
            def build_fragment(self, parent_frag: "ClockSpectroscopyBase"):
                self.parent = parent_frag

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                self.parent.core.break_realtime()
                delay(self.parent.clock_delivery_preempt_time.get())

                self.parent.prepare_clock_delivery_aom()

        self.setattr_fragment(
            "turn_on_clock_delivery_aom", TurnOnClockDeliveryAOM, self
        )

        self.setattr_fragment(
            "clock_down_default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[],
                urukul_beam_infos=[
                    CLOCK_DOWN_BEAM_INFO,
                ],
                use_automatic_setup=True,
                use_automatic_turnon=False,
            ),
        )
        self.clock_down_default_setter: SetBeamsToDefaults

    def host_setup(self):
        super().host_setup()

        # Get param handles for the clock delivery AOM - we'll drive it manually
        # here, but if the user changed them we should respect that. We must do
        # this in host_setup because the amplitude doesn't exist at build time
        # because the fragment can't detect that it's an AD9910 because ARTIQ
        # passes it a DummyDevice. Is this a bug? Yes.
        self.clock_switch_frequency_handle: FloatParamHandle = getattr(
            self.clock_default_setter, f"frequency_{CLOCK_UP_BEAM_INFO.name}"
        )
        self.clock_switch_amplitude_handle: FloatParamHandle = getattr(
            self.clock_default_setter, f"amplitude_{CLOCK_UP_BEAM_INFO.name}"
        )

    def get_always_shown_params(self):
        # Expose the clock base frequency for convenience
        param_handles = super().get_always_shown_params()
        if self.clock_delivery_handles.frequency_handle not in param_handles:
            param_handles.append(self.clock_delivery_handles.frequency_handle)
        param_handles.remove(self.spectroscopy_clock_delivery_setpoint)
        return param_handles

    @portable
    def set_clock_up_dds(self, frequency: float, amplitude: float, phase: float = 0.0):
        """
        Set the up-beam clock DDS and record the commanded frequency.

        Thin wrapper around ``clock_up_dds.set`` that also updates the
        frequency-tracking state read by PulseDMARecording.register_pulse,
        so call sites never have to track the frequency separately.
        """
        self.clock_up_dds.set(frequency=frequency, amplitude=amplitude, phase=phase)
        self._tracked_up_dds_freq = frequency

    @portable
    def set_clock_down_dds(
        self, frequency: float, amplitude: float, phase: float = 0.0
    ):
        """
        Set the down-beam clock DDS and record the commanded frequency.

        See :meth:`set_clock_up_dds`.
        """
        self.clock_down_dds.set(frequency=frequency, amplitude=amplitude, phase=phase)
        self._tracked_down_dds_freq = frequency

    @kernel
    def calculate_clock_delivery_freq(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        """
        Calculate the clock delivery AOM frequency for the spectroscopy pulse

        Returns:
            Frequency in Hz
        """
        return (
            self.clock_delivery_handles.frequency_handle.get()
            + self.spectroscopy_pulse_aom_detuning.get()
        )

    @kernel
    def prepare_clock_delivery_aom(self):
        """
        Ensure's the clock delivery AOM is on, configured and settled. Does not
        advance the timeline and *does* write into the past.
        """
        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time.get())
        self.clock_delivery_setter.set_suservo(
            freq=self.calculate_clock_delivery_freq(
                _t_start, self.spectroscopy_pulse_time.get()
            ),
            amplitude=self.clock_delivery_handles.initial_amplitude_handle.get(),
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        self.after_clock_delivery_setup_hook(_t_start)
        at_mu(_t_start)

    @kernel
    def after_clock_delivery_setup_hook(self, t_first_pulse_mu: int64):
        """
        Hook for actions after the clock delivery AOM is prepared

        Called after the clock delivery AOM is prepared, before the first
        spectroscopy pulse is fired. This method is passed the time that the
        first clock pulse will occur, which is in the future relative to
        `now_mu()`.

        No-op by default
        """


class ClockRabiSpectroscopyBase(ClockSpectroscopyBase):
    """
    Customizes ClockSpectroscopyBase for Rabi spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        # TODO: Why is spectroscopy_pulse_time defined seperately in ClockInterferometryBase? This should be in ClockSpectroscopyBase
        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=constants.CLOCK_PI_TIME,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after spectroscopy before imaging",
            default=constants.DELAY_AFTER_CLOCK_SPECTROSCOPY,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

    @kernel
    def do_rabi_spectroscopy(self):
        self.prepare_clock_delivery_aom()
        self.before_clock_spec_pulse_hook()
        self.fire_clock_spec_pulse()
        delay(self.delay_after_spectroscopy.get())

    @kernel
    def before_clock_spec_pulse_hook(self):
        """
        Hook for actions before the clock spectroscopy pulse is fired

        No-op by default
        """

    @kernel
    def fire_clock_spec_pulse(self):
        d = self.spectroscopy_pulse_time.get()
        self.register_pulse(is_up=True, duration_s=d)
        self.clock_up_dds.sw.on()
        delay(d)
        self.clock_up_dds.sw.off()


class ClockRabiSpectroscopyDownBeamBase(ClockSpectroscopyBase):
    """
    Customizes ClockSpectroscopyBase for Rabi spectroscopy with the down beam

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        # TODO: Why is spectroscopy_pulse_time defined seperately in ClockInterferometryBase? This should be in ClockSpectroscopyBase
        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=constants.CLOCK_DOWN_PI_TIME,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after spectroscopy before imaging",
            default=constants.DELAY_AFTER_CLOCK_SPECTROSCOPY,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

    @kernel
    def do_rabi_spectroscopy(self):
        self.prepare_clock_delivery_aom()
        self.before_clock_spec_pulse_hook()
        self.fire_clock_spec_pulse()
        delay(self.delay_after_spectroscopy.get())

    @kernel
    def before_clock_spec_pulse_hook(self):
        """
        Hook for actions before the clock spectroscopy pulse is fired

        No-op by default
        """

    @kernel
    def fire_clock_spec_pulse(self):
        d = self.spectroscopy_pulse_time.get()
        self.register_pulse(is_up=False, duration_s=d)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()


class ClockRabiSpectroscopyRedMotMixin(ClockRabiSpectroscopyBase):
    """
    Uses a clock pulse for spectroscopy after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_red_mot_hook`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.do_rabi_spectroscopy()


class ClockRabiSpectroscopyDipoleTrapMixin(
    ClockRabiSpectroscopyBase, DipoleTrapWithExperimentBase
):
    """
    Implements clock Rabi spectroscopy after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_rabi_spectroscopy()


class ClockRabiSpectroscopyDownBeamDipoleTrapMixin(
    ClockRabiSpectroscopyDownBeamBase, DipoleTrapWithExperimentBase
):
    """
    Implements down beam clock Rabi spectroscopy after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_rabi_spectroscopy()
