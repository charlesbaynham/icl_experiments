import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.constants import DELAY_BETWEEN_RTIO_EVENTS
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.fragments.painted_pulse import (
    GravityAndDiffractionCompensatedQuadraticShapedPulse,
)

PAINTING_URUKUL_CHANNEL = "urukul9910_aom_1064_painting"
SU_SERVO_STABILISE_TIME = 200e-6  # time for the suservo to stabilise

logger = logging.getLogger(__name__)


class MatterwaveLensingInBothDirection(DipoleTrapWithExperiment):
    """
    Mixin which switches on both the painted quadratic and up dipole potential during the dipole trap loading sequence to matterwave collimate them.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "matterwave_collimation_time_1064",
            FloatParam,
            description="Holding time for matterwave collimating in vertical direction",
            unit="ms",
            default=1e-3,
            min=0.0,
            max=100,
        )

        self.setattr_param(
            "matterwave_collimation_time_813",
            FloatParam,
            description="Holding time for matterwave collimating in horizontal direction",
            unit="ms",
            default=1e-3,
            min=0.0,
            max=100,
        )

        self.setattr_fragment(
            "painter_driver",
            GravityAndDiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=PAINTING_URUKUL_CHANNEL,
            automatic_trigger=True,
        )

        self.matterwave_collimation_time_1064: FloatParamHandle
        self.matterwave_collimation_time_813: FloatParamHandle

        # Calculate the time difference between the two pulses
        self.delta_time = abs(
            self.matterwave_collimation_time_1064.get()
            - self.matterwave_collimation_time_813.get()
        )

        # make two ordered lists,
        self.times = [
            self.matterwave_collimation_time_1064.get(),
            self.matterwave_collimation_time_813.get(),
        ]

        self.sequence_on = [
            self.dipole_beam_controller.turn_on_painter_suservo(),
            self.dipole_beam_controller.turn_on_vertical_up_suservo(),
        ]

        # order by longest time
        if self.times[0] < self.times[1]:
            self.times.reverse()
            self.sequence_on.reverse()

    @kernel
    def matterwave_collimate_hook(self):

        self.sequence_on[0]()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.dipole_beam_controller.turn_off_dipole_beams()
        delay(self.delta_time)
        self.sequence_on[1]()
        delay(self.times[1])
        self.dipole_beam_controller.turn_off_vertical_up_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.dipole_beam_controller.turn_off_painter_suservo()


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
            unit="ms",
            default=1e-3,
            min=0.0,
            max=100,
        )

        self.setattr_fragment(
            "painter_driver",
            GravityAndDiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=PAINTING_URUKUL_CHANNEL,
            automatic_trigger=True,
        )

        self.matterwave_collimation_time: FloatParamHandle

    @kernel
    def matterwave_collimate_hook(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        delay(200e-6)  # Wait for the suservo to stabilise
        # Then switch off the dipole beam
        self.dipole_beam_controller.turn_off_dipole_beams()
        delay(self.matterwave_collimation_time.get())
        self.dipole_beam_controller.turn_off_painter_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
