import logging

from repository.lib.constants import DELAY_BETWEEN_RTIO_EVENTS
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam, FloatParamHandle
from repository.lib.experiment_templates.dipole_trap_experiment import DipoleTrapWithExperiment
from repository.lib.fragments.painted_pulse import DiffractionCompensatedQuadraticShapedPulse


logger = logging.getLogger(__name__)

class PaintedMatterwaveLensingMixin(DipoleTrapWithExperiment):
    """
    Mixin which switches on the painted quadratic potential during the dipole trap loading sequence.
    """
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "matterwave_collimation_time",
            FloatParam,
            description="Holding time for matterwave collimation",
            unit="us",
            default=1,
            min=0.0,
            max=100,
        )

        self.setattr_fragment(
            "painter_driver",
            DiffractionCompensatedQuadraticShapedPulse,
            automatic_trigger = True
        )

        # Do we need to do the following line? Should be triggered in device setup...
        self.painter_driver : DiffractionCompensatedQuadraticShapedPulse
        self.matterwave_collimation_time : FloatParamHandle
    
    @kernel
    def matterwave_collimate_hook(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        # Then switch off the dipole beam
        self.dipole_beam_controller.turn_off_dipole_beams()
        delay(self.matterwave_collimation_time.get())
        self.dipole_beam_controller.turn_off_painter_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
