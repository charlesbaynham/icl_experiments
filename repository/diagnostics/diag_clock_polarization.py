r"""
Diagnostic 4 - Clock beam polarization (field-angle scan in the x-z plane).

The clock beam polarization is fixed by the optics and lies along the cavity
axis (x), per the lab notes. The *quantization field* the clock atoms actually
experience at the spectroscopy pulse is the evaporation field-ramp end value,
which on the live assembled ``ClockSpecPulseRatioFrag`` is
``ramp_during_evap_phase.bias_field_{x,y,z}_end`` =
**(-0.81, -0.009, -0.69) A** - dominantly along x (the polarization / cavity
axis) but with a *large vertical (z) component*. It is therefore NOT in the
radial (x-y) plane; the plane that actually contains the polarization axis and
the field tilt is the **x-z plane**.

This diagnostic probes the polarization purity by an ANGULAR scan of the bias
field **in the x-z plane** (Charles's decision; the radial x-y scan was rejected
because it would not rotate around the true field). At each angle θ the field
direction is rotated at fixed magnitude while the clock is driven hard on
resonance, and the excitation is recorded:

    x = |B| * cos(θ)
    z = z_nominal + |B| * sin(θ)
    y = y_nominal   (held)

with ``field_magnitude`` |B| ≈ 0.81 A and ``field_z_nominal`` = -0.69 A (the
operating point), so θ=0 reproduces ~the normal operating field along +x (the
polarization axis) and θ sweeps the field direction through the x-z plane.

The field is re-set **per shot in the kernel** via the proper
``chamber_2_field_setter.set_all_fields`` wrapper (never raw DDS/switches), with a
settling delay before the clock pulse (compensation coils take ms to settle).
NOTE: at this point in the sequence the trap has already been released, so the
settle happens in free-fall - acceptable for a direction scan, accepted by
Charles.

Result = excitation vs field angle: the angle of maximum excitation = the
effective polarization axis; the residual excitation at the orthogonal angle =
the polarization-purity diagnostic. Plot in polar coordinates (angle = field
direction θ, radius = excitation) for the figure-of-eight signature centred on
the polarization axis (done in the analysis notebook).

Default-runnable: submitting with ``arguments={}`` scans ``field_angle_deg``
0->360° (37 points, 10° step) at |B|=0.81 A, driving the clock hard on resonance
(short pulse at the reference setpoint), EM gain on, up beam.

SAFETY: the ``DISABLE_EM_GAIN`` interlock is never touched (gain only via
``em_gain_enabled``); field is set only through the ``set_all_fields`` wrapper;
coil currents stay within the coil limits by construction (|x| <= |B| = 0.81 and
z in [z_nom-|B|, z_nom+|B|] = [-1.50, +0.12] A). On surrender the caller resets
coils to nominal, since a field-angle scan leaves the coils at its last angle.
"""

import logging

import numpy as np
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import OnlineFit
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.clock_spectroscopy.clock_spectroscopy_pulse_ratio import (
    ClockSpecPulseRatioFrag,
)
from repository.lib.experiment_templates.default_scan import DefaultScanAxis
from repository.lib.experiment_templates.default_scan import make_default_scan_exp

logger = logging.getLogger(__name__)

# Default in-plane field magnitude (A) and the nominal vertical (z) offset (A).
# |B| ~ the in-plane projection of the operating clock field; z_nominal = the
# operating vertical bias. Defaults reproduce ~the operating field at theta=0.
_DEFAULT_FIELD_MAGNITUDE_A = 0.81
_DEFAULT_Z_NOMINAL_A = -0.69

_DEG_TO_RAD = 3.141592653589793 / 180.0


class ClockPolarizationDiagnosticFrag(ClockSpecPulseRatioFrag):
    """Diagnostic 4 - clock polarization via an x-z-plane field-angle scan.

    Wraps ``ClockSpecPulseRatioFrag``: drives the clock hard on resonance and, at
    each ``field_angle_deg`` θ, re-sets the bias field to
    ``(|B|cosθ, y_nom, z_nom + |B|sinθ)`` via the ``set_all_fields`` wrapper with a
    settling delay, then measures excitation. See module docstring.
    """

    def build_fragment(self):
        super().build_fragment()

        # On resonance for the strongest, cleanest excitation reading.
        self.override_param("extra_clock_detuning", 0.0)

        # Up beam (default) for the polarization probe.
        self.override_param("use_down_beam", False)

        # EM gain on by default (normalised FK clock readout needs it). Enabled
        # only via the experiment flag; DISABLE_EM_GAIN never touched.
        self.override_param("em_gain_enabled", True)
        self.override_param("em_gain", 30.0)

        # Field-angle scan axis (degrees) - the polarization probe axis.
        # No unit (scale 1) so the stored value IS degrees - 'deg' is not a
        # defined artiq.language.units scale, and a unitless param keeps the scan
        # range (0..360) and the kernel deg->rad conversion unambiguous.
        self.setattr_param(
            "field_angle_deg",
            FloatParam,
            "Bias-field direction in the x-z plane, in DEGREES: "
            "x=|B|cos, z=z_nom+|B|sin, y held nominal",
            default=0.0,
        )
        self.field_angle_deg: FloatParamHandle

        # In-plane field magnitude |B| (A).
        self.setattr_param(
            "field_magnitude",
            FloatParam,
            "Magnitude |B| of the rotated in-plane bias field",
            default=_DEFAULT_FIELD_MAGNITUDE_A,
            unit="A",
        )
        self.field_magnitude: FloatParamHandle

        # Nominal vertical (z) offset about which the field is rotated (A).
        self.setattr_param(
            "field_z_nominal",
            FloatParam,
            "Nominal z (vertical) offset about which the field is rotated",
            default=_DEFAULT_Z_NOMINAL_A,
            unit="A",
        )
        self.field_z_nominal: FloatParamHandle

        # Settling time for the compensation coils after the per-shot field
        # re-set, before the clock pulse (coils take ms to settle).
        self.setattr_param(
            "field_angle_settling_time",
            FloatParam,
            "Coil settling time after the per-shot field re-set",
            default=10e-3,
            unit="ms",
        )
        self.field_angle_settling_time: FloatParamHandle

    @kernel
    def _set_rotated_field(self):
        """Re-set the bias field to the rotated x-z direction for this shot.

        Uses the proper chamber_2_field_setter.set_all_fields wrapper (never raw
        DDS). y is held at the nominal blue-MOT bias; x/z are rotated in-plane.
        """
        theta = self.field_angle_deg.get() * _DEG_TO_RAD
        b = self.field_magnitude.get()
        x = b * np.cos(theta)
        z = self.field_z_nominal.get() + b * np.sin(theta)
        y = self.blue_3d_mot.chamber_2_bias_y.get()
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.spectroscopy_field_gradient.get(),
            x,
            y,
            z,
        )
        # Let the compensation coils settle before the field-sensitive pulse.
        delay(self.field_angle_settling_time.get())

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Rotate the quantization field for this angle, settle, then run the
        # standard clock shelving + spectroscopy sequence.
        self._set_rotated_field()
        super().do_experiment_after_dipole_trap_hook()

    def get_default_analyses(self):
        # Excitation vs field angle. A Cartesian trace; the polar figure-of-eight
        # is produced in the analysis notebook (tag_plot, RID baked in).
        return [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.field_angle_deg,
                    "y": self.excitation_fraction,
                },
            )
        ]


# Default-runnable field-angle scan, 0..360 deg, 10 deg step (37 points incl.
# both endpoints), 2 repeats.
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
