import logging
from typing import Optional

import numpy as np
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
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
            default=0.8,
            min=0.0,
            max=0.999,
        )
        self.epsilon: FloatParamHandle

        self.setattr_param(
            "mod_depth",
            FloatParam,
            description="Modulation depth of the scan",
            default=1e3,
            unit="kHz",
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
