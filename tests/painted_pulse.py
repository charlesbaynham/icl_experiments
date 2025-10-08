import numpy as np
from scipy.optimize import root_scalar
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
from scipy.stats import beta

from repository.lib.fragments.pulse_shaping import ShapedPulse

class DiffractionCompensatedQuadratic(ShapedPulse):
    def build_fragment(self, *args, **kwargs):
        self.setattr_param(
            "epsilon",
            FloatParam,
            description="Efficiency of the AOM at the edge of the pulse",
            default=0.8,
            min=0.,
            max=0.999,
        )

        self.epsilon: FloatParamHandle

        self.__setattr__param(
            "mod_depth",
            FloatParam,
            description="Modulation depth of the scan",
            default=1,
            min=1.,
            max=20.,
        )

        self.mod_depth: FloatParamHandle

        # Kernel params
        self._old_alpha = -1.0
        self._old_beta = -1.0

        return super().build_fragment(*args, **kwargs)

    def generate_amplitudes_and_phases(self, n_words) -> np.ndarray:
        """
        Generate the diffraction compensated frequency modulated pulse.

        The output will be normalized to 0 -> +1.
        """

        m = np.sqrt(1 - self.epsilon.get())
        a = self.mod_depth.get()
        relation = lambda f, v : lambda t: a * (m**2 - 1) * np.arctanh(m * f / a) + m * f - m**3 * v * t
        t

        t = np.linspace(0, 1, n_words)
        amplitude = beta(self.alpha.get(), self.beta_param.get()).pdf(t)

        amplitude /= max(amplitude)

        phase = np.zeros_like(amplitude)

        return amplitude, phase


    @kernel
    def is_recalc_needed(self) -> bool:
        """
        Check if the alpha or beta parameters have changed.
        """

        return_value = False

        if (
            self.alpha.get() != self._old_alpha
            or self.beta_param.get() != self._old_beta
        ):
            return_value = True

        self._old_alpha = self.alpha.get()
        self._old_beta = self.beta_param.get()

        return return_value