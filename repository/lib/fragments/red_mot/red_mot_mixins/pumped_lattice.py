import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
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

        self.setattr_param(
            "delay_before_spinpol_pulse",
            FloatParam,
            "Time in lattice before the spin polarization pulse",
            default=constants.TIME_IN_LATTICE_BEFORE_SPIN_POL,
            unit="ms",
        )
        self.delay_before_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "duration_spinpol_pulse",
            FloatParam,
            "Duration of the spin polarizing pulse",
            default=constants.DURATION_OF_SPIN_POL,
            unit="ms",
        )
        self.delay_before_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "delay_after_spinpol_pulse",
            FloatParam,
            "Time in lattice after the spin polarization pulse",
            default=constants.TIME_IN_LATTICE_AFTER_SPIN_POL,
            unit="ms",
        )
        self.delay_after_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "use_sigmaplus_spinpol",
            BoolParam,
            "Which spinpol beam? True = sigmaplus, False = sigmaminus",
            default=True,
        )
        self.use_sigmaplus_spinpol: BoolParamHandle

    @kernel
    def post_narrowband_hook(self):
        # Load into lattice with a bang - no ramping for now
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

        delay(self.delay_before_spinpol_pulse.get())
        # FIXME: Do pulse
        delay(self.delay_after_spinpol_pulse.get())
