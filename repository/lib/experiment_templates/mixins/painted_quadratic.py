import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.fragment import Fragment
from ndscan.experiment.parameters import FloatParam, FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from repository.lib.experiment_templates.dipole_trap_experiment import DipoleTrapWithExperiment

from repository.lib import constants

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

        self.matterwave_collimation_time : FloatParamHandle
    
    @kernel
    def matterwave_collimate_hook(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        # Then switch off the dipole beam
        self.dipole_beam_controller.turn_off_dipole_beams()
        delay(self.matterwave_collimation_time.get())
        self.dipole_beam_controller.turn_off_painter_suservo()
