r"""
Diagnostic 4 - Clock beam polarization (in-plane x-y field-angle scan).

FIXME: This module was rewritten from the reviewer's corrected physics (PR #37)
but has NOT been validated on the live rig. The reviewer expects it to need
careful on-rig testing before it is trusted (see
``.claude/plans/diagnostics_live_test_plan.md``). This FIXME deliberately blocks
merge to master until those live checks are done; remove it only once the
diagnostic has been confirmed on hardware.

Geometry (corrected 2026-06-26)
-------------------------------
The clock beam propagates along **Z**, so its linear polarization lies in the
**x-y plane**. For a normal clock pulse the bias (quantization) field is along
**x** (the nominal field ``constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END`` is, once
the Earth's-field compensation is removed, purely ``(-1.12, 0, 0) A`` along x -
parallel to the polarization for optimal pi-transition excitation). The
polarization axis is therefore probed by rotating the field **in the x-y plane**
and reading excitation versus angle: the angle of maximum excitation is the
effective polarization axis; the modulation depth is the polarization-purity
metric.

The rotation holds the **field magnitude** (not the coil current) constant. The
per-axis coil sensitivities differ (``COIL_SENSITIVITY_{X,Y}_G_PER_A``), so a
fixed-magnitude rotation maps to *different* x and y currents::

    Bx = |B| cos(phi0 + theta)        # Gauss, |B| = nominal x-y field magnitude
    By = |B| sin(phi0 + theta)
    Ix = Bx / sens_x,  Iy = By / sens_y   # back to coil amps
    (x, y, z) = add_field_offset(Ix, Iy, 0)   # Earth's-field compensation

where phi0 is the nominal field's x-y angle, so theta=0 reproduces the normal
operating field. Holding |B| fixed keeps the Zeeman shift (hence the resonance)
unchanged across the scan.

Two variants ("trials")
-----------------------
``ClockPolarizationInTrapDiagnostic`` (Approach 1): rotate the field **in-trap**
(adiabatic sub-ramp overriding the normal ramp endpoint), skip velocity selection,
and fire a single weak **pi/4** pulse on the whole thermal cloud immediately after
release. The rotated quantization field persists through release into the pulse.

``ClockPolarizationPostReleaseDiagnostic`` (Approach 2): ramp to the nominal x
field in-trap as usual, release, do a **normal velocity slice** (lower shelving
setpoint), then rotate the field by the scanned angle (+/-90 deg) **after release**
and wait a scanned ``field_settle_time`` for eddy currents to die down, before a
**full-power spectroscopy pulse at the normal setpoint**. Velocity-selecting first
is what lets this variant use a full pulse rather than a weak one.

SAFETY: the ``DISABLE_EM_GAIN`` interlock is never touched (gain only via
``em_gain_enabled``); the field is set only through the ``set_bias_fields``
wrapper; the x-y magnitude is held at the nominal operating magnitude (and z at
the pure Earth-compensation value), so coil currents stay within limits.
"""

import logging
import math

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import CustomAnalysis
from ndscan.experiment import FloatChannel
from ndscan.experiment import OnlineFit
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.clock_spectroscopy.clock_spectroscopy_pulse_ratio import (
    ClockSpecPulseRatioFrag,
)
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

_DEG_TO_RAD = math.pi / 180.0

# pi/4 pulse on the unsliced thermal cloud for Approach 1 (small enough that the
# excitation tracks the polarization projection without saturating).
_DEFAULT_PULSE_AREA_FRACTION = 0.25

# Nominal applied clock-spectroscopy field (the normal adiabatic-ramp endpoint).
_FIELD_END = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END

# Physical (Earth's-field-compensated) nominal field, in amps. Removing the
# background compensation leaves the clock field essentially purely along -x.
_PHYS_X_NOMINAL, _PHYS_Y_NOMINAL, _PHYS_Z_NOMINAL = constants.calc_new_field_defaults(
    _FIELD_END[0], _FIELD_END[1], _FIELD_END[2]
)

# Per-axis current->field calibration (Gauss / Amp). SIGNED gradients: the sign
# encodes the coil polarity (whether +current produces +axis field), so the
# rotation produces the intended field direction. See COIL_SENSITIVITY_* in
# constants.py.
_SENS_X = constants.COIL_SENSITIVITY_X_G_PER_A
_SENS_Y = constants.COIL_SENSITIVITY_Y_G_PER_A

# Nominal physical field in the x-y plane, in Gauss, and its starting angle, so the
# field can be rotated at fixed magnitude with theta=0 reproducing the nominal.
_BX_NOMINAL = _PHYS_X_NOMINAL * _SENS_X
_BY_NOMINAL = _PHYS_Y_NOMINAL * _SENS_Y
_XY_FIELD_MAG = math.hypot(_BX_NOMINAL, _BY_NOMINAL)
_XY_ANGLE_0 = math.atan2(_BY_NOMINAL, _BX_NOMINAL)

# Steps in the in-trap adiabatic rotation sub-ramp (Approach 1; kernel loop bound).
_N_ROTATION_STEPS = 50


class _ClockPolarizationBaseFrag(ClockSpecPulseRatioFrag):
    """Shared setup, field-rotation maths and analyses for the two variants."""

    def build_fragment(self):
        super().build_fragment()

        # On resonance for the strongest, cleanest excitation reading. The OPLL is
        # used for gravity compensation only; no extra detuning.
        self.override_param("extra_clock_detuning", 0.0)

        # Up beam (default) for the polarization probe.
        self.override_param("use_down_beam", False)

        # EM gain on by default (normalised FK clock readout needs it). Enabled
        # only via the experiment flag; DISABLE_EM_GAIN never touched.
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

        # Field-angle scan axis (degrees) - the polarization probe axis. Unitless
        # (the stored value IS degrees); the kernel converts deg->rad.
        self.setattr_param(
            "field_angle_deg",
            FloatParam,
            "Extra in-plane (x-y) bias-field rotation in DEGREES added to the "
            "nominal clock field (theta=0 -> nominal field along -x)",
            default=0.0,
        )
        self.field_angle_deg: FloatParamHandle

    @kernel
    def _set_rotated_field(self, added_angle):
        """Set the bias field rotated by ``added_angle`` (rad) in the x-y plane.

        Holds the field magnitude at the nominal value, converts each axis back to
        coil amps via the per-axis calibration, and applies the Earth's-field
        compensation. The trap state is unchanged - this only updates the coils.
        """
        angle = _XY_ANGLE_0 + added_angle
        bx = _XY_FIELD_MAG * np.cos(angle)
        by = _XY_FIELD_MAG * np.sin(angle)
        ix = bx / _SENS_X
        iy = by / _SENS_Y
        # Earth's-field compensation via the (now @portable) constants helper;
        # physical z is held at 0, so the applied z is the pure compensation value.
        x, y, z = constants.add_field_offset(ix, iy, 0.0)
        self.ramp_during_evap_phase.chamber_2_field_setter.set_bias_fields(x, y, z)

    def get_default_analyses(self):
        # OnlineFit draws the live modulation; the CustomAnalysis below writes the
        # fitted polarization axis (and contrast) to result datasets.
        def _analyse_polarization(axis_values, result_values, analysis_results):
            angles_deg = np.array(axis_values[self.field_angle_deg], dtype=float)
            exc = np.array(result_values[self.excitation_fraction], dtype=float)

            # The modulation has 180 deg periodicity (excitation goes as cos^2 of
            # the field-polarization angle), so estimate the polarization axis from
            # the first even harmonic (robust, fit-library-free):
            #   axis = 1/2 * atan2(sum E*sin2theta, sum E*cos2theta)  (mod 180 deg)
            theta = np.deg2rad(angles_deg)
            c = float(np.sum(exc * np.cos(2.0 * theta)))
            s = float(np.sum(exc * np.sin(2.0 * theta)))
            axis_deg = math.degrees(0.5 * math.atan2(s, c)) % 180.0

            span = float(exc.max() + exc.min())
            contrast = float(exc.max() - exc.min()) / span if span > 0 else 0.0

            analysis_results["polarization_axis_deg"].push(axis_deg)
            analysis_results["polarization_contrast"].push(contrast)
            return []

        return [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.field_angle_deg,
                    "y": self.excitation_fraction,
                },
            ),
            CustomAnalysis(
                [self.field_angle_deg],
                _analyse_polarization,
                [
                    FloatChannel(
                        "polarization_axis_deg",
                        "Estimated clock polarization axis (field angle of max "
                        "excitation, mod 180 deg)",
                    ),
                    FloatChannel(
                        "polarization_contrast",
                        "Excitation modulation depth (polarization-purity metric)",
                    ),
                ],
            ),
        ]


class ClockPolarizationInTrapDiagnosticFrag(_ClockPolarizationBaseFrag):
    """Approach 1 - in-trap rotation, no velocity slice, single pi/4 pulse.

    Rotates the quantization field by the scanned angle in the x-y plane while
    still trapped (adiabatic sub-ramp overriding the normal ramp endpoint), then
    addresses the whole thermal cloud with a single weak pulse immediately after
    release. See the module docstring for the physics.
    """

    def build_fragment(self):
        super().build_fragment()

        # pi/4 pulse area (weak enough to track the polarization projection).
        self.setattr_param(
            "pulse_area_fraction",
            FloatParam,
            "Pulse area as a fraction of pi (pi/4 default: weak probe of the "
            "polarization projection on the unsliced thermal cloud)",
            default=_DEFAULT_PULSE_AREA_FRACTION,
            min=1e-3,
            max=1.0,
        )
        self.pulse_area_fraction: FloatParamHandle

        # Pulse duration sets the Fourier linewidth; area fixed by setpoint scaling.
        self.override_param("spectroscopy_pulse_time", constants.CLOCK_PI_TIME)

        # Duration of the in-trap adiabatic rotation sub-ramp (slow -> adiabatic so
        # the spin follows the field).
        self.setattr_param(
            "field_rotation_ramp_time",
            FloatParam,
            "Duration of the in-trap adiabatic field-rotation sub-ramp",
            default=20e-3,
            unit="ms",
        )
        self.field_rotation_ramp_time: FloatParamHandle

    @kernel
    def dipole_trap_evaporation_hook_ramper(self):
        # Standard adiabatic bias-field ramp to the nominal clock-spec endpoint,
        # in-trap (precalculated DMA), exactly as for a normal clock run.
        self.ramp_during_evap_phase.do_phase()
        # Override that ramp's ENDPOINT: adiabatically rotate the in-trap
        # quantization field into the scanned x-y direction *before release*, so
        # the whole (unsliced, thermal) cloud is addressed at the rotated field.
        self._rotate_field_in_trap()

    @kernel
    def _rotate_field_in_trap(self):
        """Adiabatically rotate the in-trap bias field to the scanned x-y angle."""
        theta = self.field_angle_deg.get() * _DEG_TO_RAD
        step_time = self.field_rotation_ramp_time.get() / _N_ROTATION_STEPS
        for i in range(_N_ROTATION_STEPS):
            frac = float(i + 1) / float(_N_ROTATION_STEPS)
            self._set_rotated_field(theta * frac)
            delay(step_time)

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # NO velocity selection (the whole thermal/Doppler cloud is addressed) and
        # a single weak (pi/4) clock pulse. The quantization field was already
        # rotated in-trap (dipole_trap_evaporation_hook_ramper) and persists
        # through release into the pulse.
        self.t_dipole_beams_off = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        T_clock = self.spectroscopy_pulse_time.get()
        T_ref = self.reference_pi_pulse_duration.get()
        V_ref = self.reference_clock_setpoint.get()
        f = self.pulse_area_fraction.get()

        # pi-pulse setpoint auto-scaling V = V_ref * (T_ref / T)^2, then * f^2 so
        # that Omega * T = f * pi (a pi/4 pulse by default).
        auto_setpoint = V_ref * (T_ref / T_clock) * (T_ref / T_clock) * f * f

        # Configure the delivery AOM and pre-position the OPLL, done "in the past"
        # via the preempt window then returning to _t_prep.
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

        # Fire the single pulse, gravity-compensated relative to release.
        t_start = now_mu() + self.core.seconds_to_mu(50e-6)
        total_ramp_time = self.core.mu_to_seconds(t_start - self.t_dipole_beams_off)

        if self.use_down_beam.get():
            opll_freq = (
                start_opll_offset
                - total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )
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


class ClockPolarizationPostReleaseDiagnosticFrag(_ClockPolarizationBaseFrag):
    """Approach 2 - normal velocity slice, then post-release rotation + full pulse.

    Ramps to the nominal x field in-trap, releases, does a NORMAL velocity slice at
    the nominal field, then rotates the field by the scanned angle *after release*
    and waits ``field_settle_time`` for eddy currents to decay before a full-power
    spectroscopy pulse. Velocity-selecting first is what allows the full pulse.
    """

    def build_fragment(self):
        super().build_fragment()

        # Delay between the post-release coil update and the spectroscopy pulse, so
        # eddy currents from the field rotation have time to decay.
        self.setattr_param(
            "field_settle_time",
            FloatParam,
            "Delay between the post-release field rotation (coil update) and the "
            "spectroscopy pulse, for eddy-current decay",
            default=5e-3,
            min=0.0,
            unit="ms",
        )
        self.field_settle_time: FloatParamHandle

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.t_dipole_beams_off = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        # Normal velocity slice at the nominal x field (lower shelving setpoint).
        self.clock_shelving()

        # Rotate the bias field to the scanned angle AFTER release, then wait for
        # eddy currents to settle before interrogating.
        theta = self.field_angle_deg.get() * _DEG_TO_RAD
        self._set_rotated_field(theta)
        delay(self.field_settle_time.get())

        # Full-power spectroscopy pulse at the normal setpoint (mirrors the normal
        # clock readout; gravity comp measured from the velocity-selection pulse).
        self.prepare_clock_delivery_aom()
        t_start = now_mu() + self.core.seconds_to_mu(50e-6)
        total_ramp_time = self.core.mu_to_seconds(t_start - self.get_t_start_shelving())
        T_clock = self.spectroscopy_pulse_time.get()

        if self.use_down_beam.get():
            opll_freq = (
                start_opll_offset
                - total_ramp_time * ramp_rate
                + self.extra_clock_detuning.get()
            )
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


# Approach 1: in-trap rotation, 0..360 deg, 10 deg step (37 points), 2 repeats.
ClockPolarizationInTrapDiagnostic = make_default_scan_exp(
    ClockPolarizationInTrapDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="field_angle_deg",
            start=0.0,
            stop=360.0,
            num_points=37,
        ),
    ],
    default_num_repeats=2,
)

# Approach 2: post-release rotation, -90..90 deg, 10 deg step (19 points), 2
# repeats. field_settle_time is a separate scan axis (override from the dashboard
# to characterise the eddy-current decay at a fixed angle).
ClockPolarizationPostReleaseDiagnostic = make_default_scan_exp(
    ClockPolarizationPostReleaseDiagnosticFrag,
    default_axes=[
        DefaultScanAxis(
            param="field_angle_deg",
            start=-90.0,
            stop=90.0,
            num_points=19,
        ),
    ],
    default_num_repeats=2,
)
