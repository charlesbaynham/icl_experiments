import logging

from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam

logger = logging.getLogger(__name__)


def add_spectroscopy_params(frag: Fragment):
    """
    Adds parameters for controlling a spectroscopy pulse to a Fragment
    """

    frag.spectroscopy_pulse_time = frag.setattr_param(
        "spectroscopy_pulse_time",
        FloatParam,
        "Length of spectroscopy pulse",
        default=50e-6,
        unit="us",
    )

    frag.spectroscopy_pulse_aom_detuning = frag.setattr_param(
        "spectroscopy_pulse_aom_detuning",
        FloatParam,
        "Frequency detuning of AOM during spectroscopy pulse",
        default=0,
        unit="kHz",
    )

    frag.spectroscopy_pulse_aom_amplitude = frag.setattr_param(
        "spectroscopy_pulse_aom_amplitude",
        FloatParam,
        "Amplitude of delivery AOM during spectroscopy pulse. SUServoing is disabled",
        default=1.0,
        min=0.0,
        max=1.0,
    )
