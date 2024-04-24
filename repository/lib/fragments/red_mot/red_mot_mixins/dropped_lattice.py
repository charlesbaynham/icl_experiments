import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


class DroppedPumpedLatticeMixin(RedMOTWithExperiment):
    """
    Loads atoms into a lattice, pumps them into a stretched state then drops
    them by quickly ramping down the lattice intensity

    This Mixin overrides the :meth:`~post_narrowband_hook` from
    :class:`~RedMOTWithExperiment` load atoms into a lattice at the end of the
    narrowband red MOT, pumping them using the spin polarisation beam then
    dropping them by ramping down the lattice intensity. The "expansion time"
    begins from the end of the ramp down.

    This is a Mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.
    """

    def build_fragment(self):
        super().build_fragment()

        # FIXME add params here

        # self.setattr_param(
        #     "delay_between_fluoresence_pulses",
        #     FloatParam,
        #     "Delay after first fluorescence pulse before second",
        #     default=1e-3,
        #     unit="ms",
        # )
        # self.delay_between_fluoresence_pulses: FloatParamHandle

        # self.setattr_param(
        #     "delay_before_background_pulse",
        #     FloatParam,
        #     "Delay after final fluorescence pulse before background measurement",
        #     default=10e-3,
        #     unit="ms",
        # )
        # self.delay_before_background_pulse: FloatParamHandle

    @kernel
    def post_narrowband_hook(self):
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
