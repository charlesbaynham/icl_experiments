import logging

from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class SpectroscopyParamsMixin(RedMOTWithExperiment):
    """
    Adds parameters for controlling a spectroscopy pulse

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * None
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=50e-6,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during spectroscopy pulse",
            default=0,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_amplitude",
            FloatParam,
            "Amplitude of delivery AOM during spectroscopy pulse. SUServoing is disabled",
            default=1.0,
            min=0.0,
            max=1.0,
        )
        self.spectroscopy_pulse_aom_amplitude: FloatParamHandle
