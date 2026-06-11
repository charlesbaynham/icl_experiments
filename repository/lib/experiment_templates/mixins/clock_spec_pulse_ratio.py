import logging
from typing import TYPE_CHECKING

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutBase,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTBase

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]
ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
start_opll_offset = constants.URUKULED_BEAMS["698_clock_OPLL_offset"].frequency


class CompensatedClockSpecMixin(
    ClockShelvingAndClearoutBase,
    LMTBase,
    DipoleTrapWithExperimentBase,
):
    """
    Clock spectroscopy from XODT with gravity compensation and calibrated intensity

    Sequence (called from do_experiment_after_dipole_trap_hook):
      1. Velocity-selective pulse, duration T_sel = T_clock * pulse_ratio
      2. Clock spectroscopy pulse via fire_lmt_pulse with gravity-compensated
         static OPLL (same mechanism as LMT series)

    The clock delivery AOM setpoint is derived from reference parameters via
    the Rabi-frequency / power relationship (Omega \\propto sqrt(P)):
      V_clock = V_ref * (T_ref / T_clock)^2

    OPLL exclusively controls the clock frequency; switch DDSes are kept at
    their default frequencies throughout.
    """

    if TYPE_CHECKING:

        def DMA_initialization_checkpoint_evap_with_field_ramp(self) -> None: ...

        def DMA_initialization_checkpoint_loading_xodt_mot(self) -> None: ...

        def DMA_initialization_checkpoint_xodt_molasses(self) -> None: ...

        def DMA_initialization_checkpoint_adiabatic_cooling(self) -> None: ...

        def DMA_initialization_checkpoint_painter_on(self) -> None: ...

        def post_sequence_cleanup_checkpoint_andor(self) -> None: ...

        def post_sequence_cleanup_checkpoint_loading(self) -> None: ...

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "pulse_ratio",
            FloatParam,
            "Ratio T_sel / T_clock: selection duration = clock duration * pulse_ratio",
            default=constants.CLOCK_SHELVING_PULSE_TIME / constants.CLOCK_PI_TIME,
            min=1e-9,
        )
        self.pulse_ratio: FloatParamHandle

        self.setattr_param(
            "reference_pi_pulse_duration",
            FloatParam,
            "Reference pi-pulse duration used to derive the auto-calculated setpoint",
            default=constants.CLOCK_PI_TIME,
            unit="us",
        )
        self.reference_pi_pulse_duration: FloatParamHandle

        self.setattr_param(
            "reference_clock_setpoint",
            FloatParam,
            "Clock delivery setpoint at the reference pi-pulse duration",
            default=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            min=0.0,
            unit="V",
        )
        self.reference_clock_setpoint: FloatParamHandle

        # Disable delivery AOM detuning for simplicity
        self.override_param("spectroscopy_pulse_aom_detuning", 0.0)
        self.override_param("shelving_pulse_aom_detuning", 0.0)

        # This parameter is unused - we do it manually:
        self.override_param("down_pulses_duration", 0.0)

        self.setattr_param(
            "extra_clock_detuning",
            FloatParam,
            "Extra scannable detuning for clock spectroscopy (added to OPLL frequency)",
            default=0.0,
            unit="kHz",
        )
        self.extra_clock_detuning: FloatParamHandle

        self.setattr_param(
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after clock pulse before imaging",
            default=constants.DELAY_AFTER_CLOCK_SPECTROSCOPY,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

        self.setattr_param(
            "use_down_beam",
            BoolParam,
            "Use the down beam instead of the up beam for clock pulses",
            default=False,
        )
        self.use_down_beam: BoolParamHandle

    @kernel
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_dipole_trap_default()
        self.DMA_initialization_checkpoint_evap_with_field_ramp()
        self.DMA_initialization_checkpoint_loading_xodt_mot()
        self.DMA_initialization_checkpoint_xodt_molasses()
        self.DMA_initialization_checkpoint_adiabatic_cooling()
        self.DMA_initialization_checkpoint_painter_on()

    @kernel
    def prepare_clock_delivery_aom(self):
        """
        Override ClockSpectroscopyBase.prepare_clock_delivery_aom to use an
        auto-calculated setpoint derived from reference pi-pulse parameters:
          V_clock = V_ref * (T_ref / T_clock)^2
        """
        T_clock = self.spectroscopy_pulse_time.get()
        T_ref = self.reference_pi_pulse_duration.get()
        V_ref = self.reference_clock_setpoint.get()
        auto_setpoint = V_ref * (T_ref / T_clock) * (T_ref / T_clock)

        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time.get())

        # Set delivery suservo to configure the attenuation and lock state - setpoint and freq and handled by set_clock_delivery_aom
        self.clock_delivery_setter.set_suservo(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            amplitude=self.clock_delivery_handles.initial_amplitude_handle.get(),
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=auto_setpoint,
            enable_iir=True,
        )
        self.set_clock_delivery_aom(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            setpoint_v=auto_setpoint,
        )

        # Set OPLL for the frequency
        self.set_clock_opll(
            freq=start_opll_offset + self.extra_clock_detuning.get(),
        )
        self.after_clock_delivery_setup_hook(_t_start)
        at_mu(_t_start)

    @kernel
    def clock_shelving(self):
        """
        Override ClockShelvingAndClearoutBase.clock_shelving to use
        T_sel = spectroscopy_pulse_time * pulse_ratio instead of shelving_pulse_time.

        Also uses stop_clock_opll_ramp() (tracking wrapper) instead of calling
        the ramper directly.
        """
        T_sel = self.spectroscopy_pulse_time.get() * self.pulse_ratio.get()
        T_ref = self.reference_pi_pulse_duration.get()
        V_ref = self.reference_clock_setpoint.get()

        auto_setpoint = V_ref * (T_ref / T_sel) * (T_ref / T_sel)
        opll_frequency = (
            start_opll_offset  # No extra offset - that's just for the spectroscopy
        )

        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time_shelving.get())
        self.set_clock_delivery_aom(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            setpoint_v=auto_setpoint,
        )
        self.set_clock_opll(
            freq=opll_frequency,
        )
        at_mu(_t_start)

        self.t_velocity_slicing_pulse_centre_mu = _t_start + self.core.seconds_to_mu(
            T_sel / 2
        )

        if self.use_down_beam.get():
            # Ramp to compensate gravity
            self.start_clock_opll_ramp(
                ramp_rate,
                opll_frequency - 1e6,
                opll_frequency,
                wave_type=2,
            )
            self.register_pulse(is_up=False, duration_s=T_sel)
            self.clock_down_dds.sw.on()
            delay(T_sel)
            self.clock_down_dds.sw.off()
        else:
            # Ramp to compensate gravity
            self.start_clock_opll_ramp(
                ramp_rate,
                opll_frequency,
                opll_frequency + 2e6,
                wave_type=1,
            )
            self.register_pulse(is_up=True, duration_s=T_sel)
            self.clock_up_dds.sw.on()
            delay(T_sel)
            self.clock_up_dds.sw.off()

        delay_mu(int64(self.core.ref_multiplier))
        self.stop_clock_opll_ramp()

        delay(constants.DEFAULT_DELIVERY_SETTLING_DURATION)

        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.shelving_pulse_clearout_duration.get(),
            ignore_final_shutters=True,
        )

    @kernel
    def get_t_start_shelving(self) -> int64:
        """
        Override LMTBase.get_t_start_shelving to return the start time of the
        velocity-selection pulse, so that fire_lmt_pulse computes the correct
        gravity-compensation total_ramp_time.
        """
        T_sel = self.spectroscopy_pulse_time.get() * self.pulse_ratio.get()
        return self.t_velocity_slicing_pulse_centre_mu - self.core.seconds_to_mu(
            T_sel / 2
        )

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.t_dipole_beams_off = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        # Velocity-selective pulse (duration = T_clock * pulse_ratio)
        self.clock_shelving()

        # Reconfigure delivery AOM for spectroscopy (auto-calculated setpoint)
        self.prepare_clock_delivery_aom()

        # Clock spectroscopy pulse via fire_lmt_pulse with gravity-compensated OPLL.
        # total_ramp_time is measured from the start of the selection pulse,
        # matching the convention used by lmt_series / lmt_series_start_up.
        t_start = now_mu() + self.core.seconds_to_mu(50e-6)
        total_ramp_time = self.core.mu_to_seconds(t_start - self.get_t_start_shelving())
        T_clock = self.spectroscopy_pulse_time.get()

        if self.use_down_beam.get():
            opll_freq = (
                start_opll_offset
                - total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )
        else:
            opll_freq = (
                start_opll_offset
                + total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )

        if self.use_down_beam.get():
            # ramp the offset downwards TODO: For some reason the OPLL setting
            # is commented out in the `fire_lmt_pulse` method in the LMT module.
            # Until it's restored, we do it manually here
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                opll_freq - 1e6,
                opll_freq,
                wave_type=2,
            )
            self.register_pulse(is_up=False, duration_s=T_clock)
            self.clock_down_dds.sw.on()
            delay(T_clock)
            self.clock_down_dds.sw.off()
        else:
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                opll_freq,
                opll_freq + 2e6,
                wave_type=1,
            )
            self.register_pulse(is_up=True, duration_s=T_clock)
            self.clock_up_dds.sw.on()
            delay(T_clock)
            self.clock_up_dds.sw.off()

        delay(self.delay_after_spectroscopy.get())

    @kernel
    def post_sequence_cleanup_checkpoint_shelving(self):
        """
        Extended cleanup: stop any DRG ramp and reset static OPLL to 80 MHz
        via tracking wrappers (not the raw ramper).
        """
        self.stop_clock_opll_ramp()
        self.set_clock_opll(start_opll_offset)

    @kernel
    def post_sequence_cleanup_checkpoint(self):
        self.post_sequence_cleanup_checkpoint_subfragments()
        self.post_sequence_cleanup_checkpoint_base()
        self.post_sequence_cleanup_checkpoint_andor()
        self.post_sequence_cleanup_checkpoint_shelving()
        self.post_sequence_cleanup_checkpoint_loading()
