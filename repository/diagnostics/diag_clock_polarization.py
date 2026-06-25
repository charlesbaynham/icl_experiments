r"""
Diagnostic 4 - Clock beam polarization (in-trap field-angle scan in the x-z plane).

FIXME: This module was rewritten from the reviewer's corrected physics (PR #28)
but has NOT been validated on the live rig. The reviewer expects it to need
careful on-rig testing before it is trusted (see
``.claude/plans/diagnostics_live_test_plan.md``). This FIXME deliberately blocks
merge to master until those live checks are done; remove it only once the
diagnostic has been confirmed on hardware.

Corrected physics (supersedes the earlier free-fall field-set approach)
-----------------------------------------------------------------------
For normal clock pulses the bias (quantization) field is **adiabatically ramped
while the atoms are still trapped** in the dipole trap, from the **Y** direction
used for spin polarization to the **clock-spectroscopy** endpoint
``constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END`` ~ (-0.81, -0.009, -0.69) A
(dominantly along x - the clock-beam polarization / cavity axis - with a large
vertical z component). The atomic spin follows this slow rotation adiabatically.

To probe the polarization, this diagnostic **overrides the endpoint of that
adiabatic ramp**: after the normal in-trap ramp completes, the in-trap bias field
is adiabatically rotated *further*, by a scanned angle theta in the x-z plane (the
plane containing both the polarization axis and the operating field tilt), at
fixed x-z magnitude::

    x = |B| * cos(phi0 + theta)
    z = |B| * sin(phi0 + theta)
    y = y_nominal   (held)

where phi0 is the nominal field's x-z angle and |B| its x-z magnitude, so theta=0
reproduces the normal operating field. The rotation is done **in-trap, before
release**, via the proper ``chamber_2_field_setter.set_bias_fields`` wrapper as a
stepped adiabatic sub-ramp - never a post-release free-fall jump (which the
earlier version did, and which the reviewer rejected).

Because there is **no velocity selection / shelving** here, the *whole* thermal
(Doppler-broadened, unsliced) cloud is addressed. A single **pi/4 pulse** on
resonance then drives the clock transition; the excitation depends on the angle
between the (fixed) clock-beam polarization and the rotated quantization field.

Result = excitation vs field angle: the angle of maximum excitation is the
effective polarization axis; the modulation depth is the polarization-purity
diagnostic. The fitted polarization axis (and contrast) are written to result
datasets by a ``CustomAnalysis``; a live ``OnlineFit`` plots the modulation.

SAFETY: the ``DISABLE_EM_GAIN`` interlock is never touched (gain only via
``em_gain_enabled``); the field is set only through the ``set_bias_fields``
wrapper; coil currents stay within the coil limits by construction (the x-z
magnitude is held at the nominal operating magnitude, y at nominal).
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

# pi/4 pulse on the unsliced thermal cloud (small enough that excitation tracks
# the polarization projection without saturating).
_DEFAULT_PULSE_AREA_FRACTION = 0.25

# Nominal in-trap clock-spectroscopy bias field (the adiabatic ramp's normal
# endpoint). The diagnostic rotates the field about the origin in the x-z plane
# starting from this point, holding the x-z magnitude (and y) at nominal.
_FIELD_END = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END
_X_NOMINAL = _FIELD_END[0]
_Y_NOMINAL = _FIELD_END[1]
_Z_NOMINAL = _FIELD_END[2]

# x-z magnitude and starting angle of the nominal field, so theta=0 reproduces it.
_XZ_MAGNITUDE = math.hypot(_X_NOMINAL, _Z_NOMINAL)
_XZ_ANGLE_0 = math.atan2(_Z_NOMINAL, _X_NOMINAL)

# Number of steps in the in-trap adiabatic rotation sub-ramp (kernel loop bound).
_N_ROTATION_STEPS = 50


class ClockPolarizationDiagnosticFrag(ClockSpecPulseRatioFrag):
    """Diagnostic 4 - clock polarization via an in-trap x-z-plane field-angle scan.

    Wraps ``ClockSpecPulseRatioFrag``. Overrides the in-trap adiabatic bias-field
    ramp endpoint to rotate the quantization field by a scanned angle theta in the
    x-z plane (still trapped), skips velocity selection, and fires a single pi/4
    pulse on the whole thermal cloud. See the module docstring for the physics.
    """

    def build_fragment(self):
        super().build_fragment()

        # On resonance for the strongest, cleanest excitation reading. The OPLL is
        # used for gravity compensation only; no extra detuning.
        self.override_param("extra_clock_detuning", 0.0)

        # Up beam (default) for the polarization probe.
        self.override_param("use_down_beam", False)

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

        # EM gain on by default (normalised FK clock readout needs it). Enabled
        # only via the experiment flag; DISABLE_EM_GAIN never touched.
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

        # Field-angle scan axis (degrees) - the polarization probe axis. Unitless
        # (the stored value IS degrees); the kernel converts deg->rad.
        self.setattr_param(
            "field_angle_deg",
            FloatParam,
            "Extra in-trap bias-field rotation in the x-z plane, in DEGREES, "
            "added to the nominal clock field (theta=0 -> nominal field)",
            default=0.0,
        )
        self.field_angle_deg: FloatParamHandle

        # x-z magnitude held during the rotation (default = nominal field's x-z
        # magnitude, so the rotation is pure direction, no Zeeman-shift change).
        self.setattr_param(
            "field_magnitude",
            FloatParam,
            "x-z magnitude |B| held while the field direction is rotated",
            default=_XZ_MAGNITUDE,
            unit="A",
        )
        self.field_magnitude: FloatParamHandle

        # y component, held at nominal throughout the rotation.
        self.setattr_param(
            "field_y_nominal",
            FloatParam,
            "Nominal y (held) bias field during the rotation",
            default=_Y_NOMINAL,
            unit="A",
        )
        self.field_y_nominal: FloatParamHandle

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
        # Standard adiabatic Y->Z bias-field ramp to the nominal clock-spec
        # endpoint, in-trap (precalculated DMA), exactly as for a normal clock run.
        self.ramp_during_evap_phase.do_phase()
        # Override that ramp's ENDPOINT: adiabatically rotate the in-trap
        # quantization field into the scanned x-z direction *before release*, so
        # the whole (unsliced, thermal) cloud is addressed at the rotated field.
        self._rotate_field_in_trap()

    @kernel
    def _rotate_field_in_trap(self):
        """Adiabatically rotate the in-trap bias field to the scanned x-z angle.

        Steps the field from the nominal clock endpoint to
        ``(|B|cos(phi0+theta), y_nom, |B|sin(phi0+theta))`` over
        ``field_rotation_ramp_time`` using the proper ``set_bias_fields`` wrapper
        (never raw DDS). Slow enough that the atomic spin follows adiabatically;
        the trap is still on.
        """
        theta = self.field_angle_deg.get() * _DEG_TO_RAD
        magnitude = self.field_magnitude.get()
        y = self.field_y_nominal.get()

        x_target = magnitude * np.cos(_XZ_ANGLE_0 + theta)
        z_target = magnitude * np.sin(_XZ_ANGLE_0 + theta)

        step_time = self.field_rotation_ramp_time.get() / _N_ROTATION_STEPS
        for i in range(_N_ROTATION_STEPS):
            frac = float(i + 1) / float(_N_ROTATION_STEPS)
            x = _X_NOMINAL + (x_target - _X_NOMINAL) * frac
            z = _Z_NOMINAL + (z_target - _Z_NOMINAL) * frac
            self.ramp_during_evap_phase.chamber_2_field_setter.set_bias_fields(x, y, z)
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

    def get_default_analyses(self):
        # OnlineFit draws the live modulation; the CustomAnalysis below writes the
        # fitted polarization axis (and contrast) to result datasets.
        def _analyse_polarization(axis_values, result_values, analysis_results):
            angles_deg = np.array(axis_values[self.field_angle_deg], dtype=float)
            exc = np.array(result_values[self.excitation_fraction], dtype=float)

            # The pi-selection modulation has 180 deg periodicity (excitation goes
            # as cos^2 of the field-polarization angle), so estimate the
            # polarization axis from the first even harmonic (robust,
            # fit-library-free):
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


# Default-runnable in-trap field-angle scan, 0..360 deg, 10 deg step (37 points
# incl. both endpoints), 2 repeats.
ClockPolarizationDiagnostic = make_default_scan_exp(
    ClockPolarizationDiagnosticFrag,
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
