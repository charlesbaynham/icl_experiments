import logging
from typing import Optional

import numpy as np
from artiq.master.worker_impl import CCB
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
from numpy import abs
from numpy import log
from numpy import sqrt
from scipy.optimize import root_scalar

from repository.lib.fragments.pulse_shaping import FrequencyShapedPulse

logger = logging.getLogger(__name__)


class DiffractionCompensatedQuadraticShapedPulse(FrequencyShapedPulse):
    def build_fragment(
        self, automatic_trigger: Optional[bool] = False, *args, **kwargs
    ):
        self.setattr_param(
            "epsilon",
            FloatParam,
            description="Efficiency of the AOM at the edge of the pulse",
            default=0.773,
            min=0.0,
            max=0.999,
        )
        self.epsilon: FloatParamHandle

        self.setattr_param(
            "mod_depth",
            FloatParam,
            description="Modulation depth of the scan",
            default=10e6,
            unit="MHz",
            min=1.0,
            max=200e6,
        )
        self.mod_depth: FloatParamHandle

        self.setattr_param(
            "centre_frequency",
            FloatParam,
            description="Centre frequency of the shaped pulse",
            default=103e6,
            unit="MHz",
            min=0.0,
            max=4e8,
        )
        self.centre_frequency: FloatParamHandle

        # Kernel params
        self._old_frequency = -1.0
        self._old_depth = -1.0
        self._old_epsilon = -1.0

        # Do we want to automatically trigger the pulse in device_setup?
        self.automatic_trigger = automatic_trigger

        return super().build_fragment(
            centre_frequency_param_handle=self.centre_frequency, *args, **kwargs
        )

    @kernel
    def device_setup(self):
        # Rewrite the device setup
        self.device_setup_base()
        self.core.break_realtime()
        self.prepare_pulse()

        if self.automatic_trigger is True:
            self.start_output()

    def generate_frequencies(self, n_words) -> np.ndarray:
        """
        Generate the diffraction compensated frequency modulated pulse.

        The output will be normalized to 0 -> +1.
        """

        m = np.sqrt(1 - self.epsilon.get())

        if (n_words % 2) != 0:
            raise ValueError("n_words must be even")

        # Generate a numpy array of the correct size
        n_half = n_words // 2
        relation = lambda t: lambda f: (m**2 - 1) * np.arctanh(m * f) + m * f - t
        # This is a bit of a hack, we want to find the maximum value of t, so we can rearrange the above equation for t and f = 1.
        # This expression is essentially the same but without the t component!
        t_max = relation(0)(1)
        calc_ts = np.linspace(-t_max, t_max, n_half)
        roots = np.array(
            list(
                map(
                    lambda t: root_scalar(relation(t), method="newton", x0=0).root,
                    calc_ts,
                )
            )
        )
        detunings = np.zeros(2 * n_half)
        detunings[:n_half] = roots
        detunings[n_half:] = -1 * roots
        detunings *= self.mod_depth.get()

        logger.warning(detunings)

        return detunings

    @kernel
    def is_recalc_needed(self) -> bool:
        """
        Check if any of the parameters have changed.
        """

        return_value = False

        if (
            self.mod_depth.get() != self._old_depth
            or self.epsilon.get() != self._old_epsilon
        ):
            return_value = True

        self._old_depth = self.mod_depth.get()
        self._old_epsilon = self.epsilon.get()

        return return_value


class GravityAndDiffractionCompensatedQuadraticShapedPulse(FrequencyShapedPulse):
    """
    A class of pulse that generates a gravity compensated quadratic pulse with diffraction correction.

    """

    def build_fragment(
        self, automatic_trigger: Optional[bool] = False, *args, **kwargs
    ):
        self.setattr_param(
            "epsilon",
            FloatParam,
            description="Efficiency of the AOM at the edge of the pulse",
            default=0.8,
            min=0.0,
            max=0.999,
        )
        self.epsilon: FloatParamHandle

        self.setattr_param(
            "g",
            FloatParam,
            description="Gradient of gravity compensation",
            default=1,
            min=-1000.0,
            max=1000,
        )
        self.g: FloatParamHandle

        self.setattr_param(
            "curve_factor",
            FloatParam,
            description="Curvature of the trap",
            default=1,
            min=0.0,
            max=1,
        )
        self.curve_factor: FloatParamHandle

        self.setattr_param(
            "int_k",
            FloatParam,
            description="Integrated time average power",
            default=10,
            min=0.0,
            max=1e6,
        )
        self.int_k: FloatParamHandle

        self.setattr_param(
            "cubic_correction",
            FloatParam,
            description="Cubic correction term",
            default=0,
            min=-1.0,
            max=1,
        )
        self.cubic_correction: FloatParamHandle

        self.setattr_param(
            "quartic_correction",
            FloatParam,
            description="Quartic correction term",
            default=0,
            min=-1.0,
            max=1,
        )
        self.quartic_correction: FloatParamHandle

        self.setattr_param(
            "mod_depth",
            FloatParam,
            description="Modulation depth of the scan",
            default=1e6,
            unit="MHz",
            min=1.0,
            max=200e6,
        )
        self.mod_depth: FloatParamHandle

        self.setattr_param(
            "centre_frequency",
            FloatParam,
            description="Centre frequency of the shaped pulse",
            default=100e6,
            unit="MHz",
            min=0.0,
            max=4e8,
        )
        self.centre_frequency: FloatParamHandle

        self.setattr_device("ccb")
        self.ccb: CCB

        # Kernel params
        self._old_frequency = -1.0
        self._old_depth = -1.0
        self._old_epsilon = -1.0
        self._old_grav = -1.0
        self._old_curve = -1.0
        self._old_cubic = -1.0
        self._old_quartic = -1.0
        self._old_k = -1.0

        # Do we want to automatically trigger the pulse in device_setup?
        self.automatic_trigger = automatic_trigger

        return super().build_fragment(
            centre_frequency_param_handle=self.centre_frequency, *args, **kwargs
        )

    def host_setup(self):
        super().host_setup()

        n = self.num_steps.get()

        x_vals = np.linspace(-1, 1, n)
        y_vals = self.intensity_function(x_vals)

        self.set_dataset("painted_shape_x", x_vals, broadcast=True)
        self.set_dataset("painted_shape_y", y_vals, broadcast=True)

        cmd = f"${{artiq_applet}}plot_xy painted_shape_y --x painted_shape_x"
        self.ccb.issue("create_applet", "Painted Pulse Shape", cmd)

        # x_high_res = np.linspace(-1, 1, 100*n)
        # Gauss_points = self.generate_frequencies(n) / self.mod_depth.get()
        # y = [np.exp]

    @kernel
    def device_setup(self):
        # Rewrite the device setup
        self.device_setup_base()
        self.core.break_realtime()
        self.prepare_pulse()

        if self.automatic_trigger is True:
            self.start_output()

    def intensity_function(self, x):

        a, b, c = self.transform_coeffs()
        t_1 = self.cubic_correction.get()
        t_2 = self.quartic_correction.get()
        eps = self.epsilon.get()

        return (t_2 * x**4 + t_1 * x**3 + a * x**2 + b * x + c) / (1 - (1 - eps) * x**2)

    def transform_coeffs(self):
        """
        This method transforms the physics parameters into qudratic coefficients
        """

        grad = self.g.get()
        int_k = self.int_k.get()
        curvature = self.curve_factor.get()

        # Transform the coefficients
        # The |grad| allows one corner to be always at 0
        # k > 0
        j = 2 * abs(grad) + int_k

        p = (abs(grad) - j / 2) * curvature + j / 2

        coeff_a = 1.5 * (p - j / 2)
        coeff_b = grad
        coeff_c = 0.5 * (3 * j / 2 - p)

        # Ensure that we have a negative curvature in the shape of the trap.
        logger.warning("a")
        logger.warning(coeff_a)
        logger.warning("b")
        logger.warning(coeff_b)
        logger.warning("c")
        logger.warning(coeff_c)
        assert coeff_a <= 0

        return coeff_a, coeff_b, coeff_c

    def generate_frequencies(self, n_words) -> np.ndarray:
        """
        Generate the gravity and diffraction compensating frequency modulated pulse.

        The output will be normalized to 0 -> +1.
        """

        eps = self.epsilon.get()
        t_1 = self.cubic_correction.get()
        t_2 = self.quartic_correction.get()
        k_1, k_2, k_3 = self.transform_coeffs()

        if (n_words % 2) != 0:
            raise ValueError("n_words must be even")

        # Generate a numpy array of the correct size
        n_half = n_words // 2

        # You might be thinking: What is this diabolical equation!?
        # The answer is the indefinite integral of the diffraction compensated quadratic pulse solved using maxima.

        relation = (
            lambda x: -(
                ((t_1 + (1 - eps) * k_2) * log(abs((eps - 1) * x**2 + 1)))
                / (2 * eps**2 - 4 * eps + 2)
            )
            + (
                (t_2 + (eps**2 - 2 * eps + 1) * k_3 + (1 - eps) * k_1)
                * log(
                    abs((2 * eps - 2) * x - 2 * sqrt(1 - eps))
                    / abs((2 * eps - 2) * x + 2 * sqrt(1 - eps))
                )
            )
            / (2 * sqrt(1 - eps) * (eps**2 - 2 * eps + 1))
            + (
                (2 * eps - 2) * t_2 * x**3
                + (3 * eps - 3) * t_1 * x**2
                + ((6 * eps - 6) * k_1 - 6 * t_2) * x
            )
            / (6 * eps**2 - 12 * eps + 6)
        )

        t_max = relation(1)
        t_min = relation(-1)
        calc_ts = np.linspace(t_min, t_max, n_half)
        roots = np.array(
            list(
                map(
                    lambda t: root_scalar(
                        lambda x: relation(x) - t, method="newton", x0=0
                    ).root,
                    calc_ts,
                )
            )
        )
        detunings = np.zeros(2 * n_half)
        detunings[:n_half] = roots
        detunings[n_half:] = roots[::-1]
        logger.warning(detunings)
        detunings *= self.mod_depth.get()

        return detunings

    @kernel
    def is_recalc_needed(self) -> bool:
        """
        Check if any of the parameters have changed.
        """

        return_value = False

        if (
            self.mod_depth.get() != self._old_depth
            or self.epsilon.get() != self._old_epsilon
            or self.g.get() != self._old_grav
            or self.curve_factor.get() != self._old_curve
            or self.cubic_correction.get() != self._old_cubic
            or self.quartic_correction.get() != self._old_quartic
            or self.int_k.get() != self._old_k
        ):
            return_value = True

        self._old_depth = self.mod_depth.get()
        self._old_epsilon = self.epsilon.get()
        self._old_grav = self.g.get()
        self._old_curve = self.curve_factor.get()
        self._old_cubic = self.cubic_correction.get()
        self._old_quartic = self.quartic_correction.get()
        self._old_k = self.int_k.get()

        return return_value
