r"""
Clock cavity offset (up beam) and clock down-vs-up offset.

``ClockCavityOffset`` (up beam): a single weak (``pi/8``) pulse on the *unselected*
cloud, scanning the clock delivery AOM frequency with the OPLL held on the nominal
line (``extra_clock_detuning = 0``). The resonance position vs delivery frequency
calibrates the clock-cavity drift. With no velocity selection the line is
Doppler-broadened, so it is fit with a Gaussian.

``ClockDownVsUpOffset`` (down beam): the standard velocity-slice + ``pi`` pulse,
scanning ``extra_clock_detuning``. Read against the up-beam cavity calibration it
gives the down-vs-up offset; fit the Rabi (``detuned_square_pulse``) lineshape.

Both build on :class:`ClockSpecPulseRatioFrag` (loading, gravity-compensated clock
delivery, normalised fast-kinetics readout). EM gain is enabled via the
experiment's own flag; ``DISABLE_EM_GAIN`` is never touched.

Each keeps its live ``OnlineFit`` *and* a paired ``make_dataset_fit_analysis`` that
writes the fitted line centre (and width) into result datasets - the diagnosed
numbers must persist for logging/trending, not just draw on the applet.
"""

import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import OnlineFit
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.clock_spectroscopy.clock_spectroscopy_pulse_ratio import (
    ClockSpecPulseRatioFrag,
)
from repository.diagnostics.dataset_fit_analysis import FitOutput
from repository.diagnostics.dataset_fit_analysis import make_dataset_fit_analysis
from repository.lib import constants
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    CLOCK_BEAM_DELIVERY_INFO,
)
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import ramp_rate
from repository.lib.experiment_templates.mixins.clock_spec_pulse_ratio import (
    start_opll_offset,
)

logger = logging.getLogger(__name__)

_WEAK_PULSE_AREA_FRACTION = 0.125

_CAVITY_SCAN_HALF_RANGE = 30e3


class ClockCavityOffsetFrag(ClockSpecPulseRatioFrag):
    """Up-beam clock-cavity-drift calibration: single weak pulse, scan delivery
    frequency, Gaussian fit on the Doppler-broadened line."""

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "pulse_area_fraction",
            FloatParam,
            "Pulse area as a fraction of pi",
            default=_WEAK_PULSE_AREA_FRACTION,
            min=1e-3,
            max=1.0,
        )
        self.pulse_area_fraction: FloatParamHandle

        self.override_param("use_down_beam", False)
        # OPLL held on the nominal line; the delivery AOM frequency is the scan axis.
        self.override_param("extra_clock_detuning", 0.0)

        self.override_param("spectroscopy_pulse_time", constants.CLOCK_PI_TIME)
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)
        self.override_param("blue_loading_time", 500e-3)

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Single weak pulse on the unselected cloud: no velocity slice, no second
        # interrogation pulse.
        self.t_dipole_beams_off = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        T_clock = self.spectroscopy_pulse_time.get()
        T_ref = self.reference_pi_pulse_duration.get()
        V_ref = self.reference_clock_setpoint.get()
        f = self.pulse_area_fraction.get()

        # pi setpoint scaling V = V_ref * (T_ref / T)^2, times f^2 so Omega*T = f*pi.
        auto_setpoint = V_ref * (T_ref / T_clock) * (T_ref / T_clock) * f * f

        # Configure the delivery AOM and pre-position the OPLL inside the preempt
        # window (written in the past), then return to _t_prep.
        _t_prep = now_mu()
        delay(-self.clock_delivery_preempt_time.get())
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
        self.set_clock_opll(freq=start_opll_offset + self.extra_clock_detuning.get())
        self.after_clock_delivery_setup_hook(_t_prep)
        at_mu(_t_prep)

        t_start = now_mu() + self.core.seconds_to_mu(50e-6)
        total_ramp_time = self.core.mu_to_seconds(t_start - self.t_dipole_beams_off)

        opll_freq = (
            start_opll_offset
            + total_ramp_time * ramp_rate
            + self.extra_clock_detuning.get()
        )
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

    def get_default_analyses(self):
        # OnlineFit draws the live Gaussian; make_dataset_fit_analysis additionally
        # writes the fitted line centre (and width) to result datasets.
        return [
            OnlineFit(
                "gaussian",
                data={
                    "x": self.clock_delivery_handles.frequency_handle,
                    "y": self.excitation_fraction,
                },
            )
        ] + make_dataset_fit_analysis(
            fit_type="gaussian",
            x=self.clock_delivery_handles.frequency_handle,
            y=self.excitation_fraction,
            outputs=[
                FitOutput(
                    "line_centre_aom",
                    "Fitted clock line centre on the delivery-AOM axis",
                    fit_key="x0",
                    unit="MHz",
                ),
                FitOutput(
                    "line_fwhm",
                    "Fitted Gaussian FWHM of the Doppler-broadened line",
                    fit_key="fwhm",
                    unit="kHz",
                ),
            ],
        )


class ClockDownVsUpOffsetFrag(ClockSpecPulseRatioFrag):
    """Down-beam offset vs the up-beam cavity calibration: velocity slice + pi
    pulse, scan extra_clock_detuning, Rabi-lineshape fit."""

    def build_fragment(self):
        super().build_fragment()

        self.override_param("use_down_beam", True)
        self.override_param("spectroscopy_pulse_time", constants.CLOCK_PI_TIME)
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)
        self.override_param("blue_loading_time", 500e-3)

    def get_default_analyses(self):
        # OnlineFit draws the live lineshape; make_dataset_fit_analysis additionally
        # writes the fitted down-beam line centre to a result dataset.
        return [
            OnlineFit(
                "detuned_square_pulse",
                data={
                    "x": self.extra_clock_detuning,
                    "y": self.excitation_fraction,
                },
            )
        ] + make_dataset_fit_analysis(
            fit_type="detuned_square_pulse",
            x=self.extra_clock_detuning,
            y=self.excitation_fraction,
            outputs=[
                FitOutput(
                    "line_centre_detuning",
                    "Fitted down-beam line centre (extra_clock_detuning at resonance; "
                    "read against the up-beam cavity calibration for the down-vs-up offset)",
                    fit_key="offset",
                    unit="kHz",
                ),
            ],
        )


ClockCavityOffset = make_default_scan_exp(
    ClockCavityOffsetFrag,
    default_axes=[
        DefaultScanAxis(
            param="frequency_clock_delivery",
            path="clock_default_setter",
            start=CLOCK_BEAM_DELIVERY_INFO.frequency - _CAVITY_SCAN_HALF_RANGE,
            stop=CLOCK_BEAM_DELIVERY_INFO.frequency + _CAVITY_SCAN_HALF_RANGE,
            num_points=31,
        ),
    ],
    default_num_repeats=2,
)

ClockDownVsUpOffset = make_default_scan_exp(
    ClockDownVsUpOffsetFrag,
    default_axes=[
        DefaultScanAxis(
            param="extra_clock_detuning",
            start=-100e3,
            stop=100e3,
            num_points=41,
        ),
    ],
    default_num_repeats=2,
)
