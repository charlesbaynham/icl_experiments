import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    CompensatedClockSpecMixin,
)
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import ramp_rate
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    start_opll_offset,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecPulseRatioFrag(
    CompensatedClockSpecMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Clock spectroscopy from dropped single XODT with OPLL-based gravity
    compensation and auto-scaled clock delivery setpoint.

    Selection pulse duration = clock pulse duration * pulse_ratio.
    Clock delivery setpoint auto-calculated: V = V_ref * (T_ref / T_clock)^2.
    OPLL exclusively controls clock frequency; switch DDSes are constant.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "use_down_beam",
            BoolParam,
            "Use the down beam instead of the up beam for clock pulses",
            default=False,
        )
        self.use_down_beam: BoolParamHandle

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_painter_on()

    @kernel
    def clock_shelving(self):
        T_sel = self.spectroscopy_pulse_time.get() * self.pulse_ratio.get()

        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time_shelving.get())
        self.set_clock_delivery_aom(
            freq=self.clock_delivery_handles.frequency_handle.get(),
            setpoint_v=self.shelving_clock_delivery_setpoint.get(),
        )
        self.set_clock_opll(
            freq=start_opll_offset + self.extra_clock_detuning.get(),
        )
        at_mu(_t_start)

        # Ramp upwards to compensate gravity
        self.start_clock_opll_ramp(
            ramp_rate,
            start_opll_offset + self.extra_clock_detuning.get(),
            start_opll_offset + self.extra_clock_detuning.get() + 2e6,
            wave_type=1,
        )

        self.t_velocity_slicing_pulse_centre_mu = _t_start + self.core.seconds_to_mu(
            T_sel / 2
        )

        if self.use_down_beam.get():
            self.register_pulse(is_up=False, duration_s=T_sel)
            self.clock_down_dds.sw.on()
            delay(T_sel)
            self.clock_down_dds.sw.off()
        else:
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
        opll_freq = (
            start_opll_offset
            + total_ramp_time * ramp_rate
            + self.extra_clock_detuning.get()
        )
        if self.use_down_beam.get():
            self.fire_lmt_pulse(opll_freq, "down", t_start)
        else:
            self.fire_lmt_pulse(opll_freq, "up", t_start)

        delay(self.delay_after_spectroscopy.get())

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_loading()


ClockSpecPulseRatio = make_fragment_scan_exp(ClockSpecPulseRatioFrag)
