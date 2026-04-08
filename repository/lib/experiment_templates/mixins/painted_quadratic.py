import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.constants import DELAY_BETWEEN_RTIO_EVENTS
from repository.lib.constants import PAINTING_URUKUL_CHANNEL
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import PaintedLinearRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import (
    XODTWithLinearRampAdiabaticCooling,
)
from repository.lib.fragments.painted_pulse import (
    GravityAndDiffractionCompensatedQuadraticShapedPulse,
)

SU_SERVO_STABILISE_TIME = 200e-6  # time for the suservo to stabilise

logger = logging.getLogger(__name__)


class MatterwaveLensingInBothDirection(DipoleTrapWithExperiment):
    """
    Mixin which switches on both the painted quadratic and up dipole potential during the dipole trap loading sequence to matterwave collimate them.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~matterwave_collimate_hook`
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

        # FIXME consider ram_offset flag
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

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~matterwave_collimate_hook`
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

        # FIXME remember to add a ram_offset here
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


class AdiabaticCoolingWithPaintedQuadraticMixin(DipoleTrapWithExperiment):
    """
    Mixin which adiabitically adiabatically cools the atoms from the fixed HODT into the painted HODT.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~adiabatic_cooling_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "painter_driver",
            GravityAndDiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=PAINTING_URUKUL_CHANNEL,
            automatic_trigger=True,
            ram_offset=512,
        )

        self.setattr_fragment(
            "adiabatic_cooling_ramp",
            XODTWithLinearRampAdiabaticCooling,
            enforce_binding_to_defaults=False,
        )

        self.adiabatic_cooling_ramp: XODTWithLinearRampAdiabaticCooling

        # self.setattr_fragment(
        #     "adiabatic_painter_ramp_on",
        #     PaintedLinearRamp,
        #     enforce_binding_to_defaults=False,
        # )

        # self.adiabatic_painter_ramp_on: PaintedLinearRamp

        self.setattr_param_rebind(
            "HODT_adiabatic_ramp_down_time",
            self.adiabatic_cooling_ramp,
            "duration",
            description="Duration of the HODT adiabatic ramp down time",
            unit="ms",
            default=50e-3,
            min=0.0,
        )

        self.HODT_adiabatic_ramp_down_time: FloatParamHandle

        # self.setattr_param_rebind(
        #     "Painter_adiabatic_ramp_up_time",
        #     self.adiabatic_painter_ramp_on,
        #     "duration",
        #     description="Duration of the painter adiabatic ramp up time",
        #     unit="ms",
        #     default=50e-3,
        #     min=0.0,
        # )

        # self.Painter_adiabatic_ramp_up_time: FloatParamHandle

        self.adiabatic_cooling_ramp.bind_suservo_setpoint_params_to_default_beam_setter(
            self.dipole_beam_controller.all_beam_default_setter
        )

        # Set the time to the parameter value

    @kernel
    def DMA_initialization_hook_painting(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        # self.adiabatic_painter_ramp_on.precalculate_dma_handle()
        self.adiabatic_cooling_ramp.precalculate_dma_handle()

    @kernel
    def adiabatic_cooling_hook(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        # delay(DELAY_BETWEEN_RTIO_EVENTS)
        # self.adiabatic_painter_ramp_on.do_phase()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        # Do the ramp
        self.adiabatic_cooling_ramp.do_phase()
        # delay(6e-3)  # FIXME Remove this when finished testing
