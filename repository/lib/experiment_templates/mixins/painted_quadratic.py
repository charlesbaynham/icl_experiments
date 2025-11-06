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

class PaintedQuadraticDipoleMixin(DipoleTrapWithExperiment):
    """
    Mixin which switches switches on the painted quadratic potential during the dipole trap loading
    """
    def build_fragment(self):
        super().build_fragment()

    @kernel
    def dipole_trap_loading_hook(self):
        # Switch on the painter and the dipole beam
        self.dipole_beam_controller.turn_on_painter_suservo()
        self.dipole_beam_controller.turn_on_dipole_beams()