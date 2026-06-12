import logging

from artiq.coredevice.core import now_mu
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib.constants import DELAY_BETWEEN_RTIO_EVENTS
from repository.lib.constants import PAINTING_URUKUL_CHANNEL
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.dipole_trap.dipole_trap_phases import PaintedLinearRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import (
    XODTWithLinearRampAdiabaticCooling,
)
from repository.lib.fragments.painted_pulse import (
    GravityAndDiffractionCompensatedQuadraticShapedPulse,
)

SU_SERVO_STABILISE_TIME = 200e-6  # time for the suservo to stabilise

logger = logging.getLogger(__name__)

SUSERVOS_XODT = [
    "suservo_aom_1064_delivery",
    "suservo_aom_down_813",
]

SUSERVO_PAINTER = ["suservo_aom_1064_painted_delivery"]

SUSERVO_UP_813 = ["suservo_aom_up_813"]


class MatterwaveLensingInBothDirectionMixin(DipoleTrapWithExperimentBase):
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


class MatterwaveLensingVerticalBeamMixin(DipoleTrapWithExperimentBase):
    """
    Mixin which switches on the up dipole potential during the dipole trap loading sequence to matterwave collimate them.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~matterwave_collimate_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "matterwave_collimation_time_813",
            FloatParam,
            description="Holding time for matterwave collimating in horizontal direction",
            unit="ms",
            default=3e-3,
            min=0.0,
            max=100,
        )
        self.matterwave_collimation_time_813: FloatParamHandle

        self.t_delta_kick = int64(0)

    @kernel
    def matterwave_collimate_hook(self):

        self.t_delta_kick = now_mu()
        self.dipole_beam_controller.turn_on_vertical_up_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.dipole_beam_controller.turn_off_dipole_beams()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.dipole_beam_controller.turn_off_painter_suservo()

        delay(self.matterwave_collimation_time_813.get())
        self.dipole_beam_controller.turn_off_vertical_up_suservo()


class PaintedMatterwaveLensingMixin(DipoleTrapWithExperimentBase):
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
        self.matterwave_collimation_time: FloatParamHandle

        self.setattr_fragment(
            "painter_driver",
            GravityAndDiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=PAINTING_URUKUL_CHANNEL,
            automatic_trigger=True,
        )

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


class PainterRampMixin(DipoleTrapWithExperimentBase):
    """
    Mixin which adiabatically turns on the painter in the adiabatic cooling hook.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~adiabatic_cooling_hook`
    * :meth:`~post_sequence_cleanup_checkpoint`
    * :meth:`~DMA_initialisation_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        if not hasattr(self, "painter_driver_loading"):
            self.setattr_fragment(
                "painter_driver",
                GravityAndDiffractionCompensatedQuadraticShapedPulse,
                ad9910_name=PAINTING_URUKUL_CHANNEL,
                automatic_trigger=True,
                ram_offset=512,
            )
            self.painter_driver: GravityAndDiffractionCompensatedQuadraticShapedPulse

        self.setattr_fragment(
            "adiabatic_painter_ramp_on",
            PaintedLinearRamp,
            enforce_binding_to_defaults=False,
        )

        self.adiabatic_painter_ramp_on: PaintedLinearRamp

        self.setattr_param_rebind(
            "Painter_adiabatic_ramp_up_time",
            self.adiabatic_painter_ramp_on,
            "duration",
            description="Duration of the painter adiabatic ramp up time",
            unit="ms",
            default=50e-3,
            min=0.0,
        )

        self.Painter_adiabatic_ramp_up_time: FloatParamHandle

        self.adiabatic_painter_ramp_on.bind_suservo_setpoint_params_to_default_beam_setter(
            self.dipole_beam_controller.all_beam_default_setter
        )

        # Set the time to the parameter value

        class PainterDMAFrag(RedMOTCheckpoints):
            def build_fragment(self, adiabatic_painter_ramp_on):
                self.adiabatic_painter_ramp_on = adiabatic_painter_ramp_on
                self.kernel_invariants = getattr(self, "kernel_invariants", set())
                self.kernel_invariants.add("adiabatic_painter_ramp_on")

            @kernel
            def DMA_initialization_checkpoint(self):
                self.DMA_initialization_checkpoint_subfragments()
                self.adiabatic_painter_ramp_on.precalculate_dma_handle()

        self.setattr_fragment(
            "painter_dma",
            PainterDMAFrag,
            adiabatic_painter_ramp_on=self.adiabatic_painter_ramp_on,
        )
        self.painter_dma: PainterDMAFrag

    @kernel
    def painter_ramp_on(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.dipole_beam_controller.turn_on_vertical_up_suservo()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        self.adiabatic_painter_ramp_on.do_phase()

    @kernel
    def adiabatic_cooling_hook(self):
        self.painter_ramp_on()


class AdiabaticCoolingWithPaintedQuadraticMixin(PainterRampMixin):
    """
    Mixin which adiabitically adiabatically cools the atoms from the fixed HODT into the painted HODT.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~adiabatic_cooling_hook`
    * :meth:`~post_sequence_cleanup_checkpoint`
    * :meth:`~DMA_initialisation_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "adiabatic_cooling_ramp",
            XODTWithLinearRampAdiabaticCooling,
            enforce_binding_to_defaults=False,
        )
        self.adiabatic_cooling_ramp: XODTWithLinearRampAdiabaticCooling

        self.setattr_param_rebind(
            "HODT_adiabatic_ramp_down_time",
            self.adiabatic_cooling_ramp,
            "duration",
            description="Duration of the HODT adiabatic ramp down time",
            unit="ms",
            default=240e-3,
            min=0.0,
        )
        self.HODT_adiabatic_ramp_down_time: FloatParamHandle

        self.adiabatic_cooling_ramp.daisy_chain_with_previous_phase(
            self.adiabatic_painter_ramp_on,
            SUSERVOS_XODT + SUSERVO_PAINTER + SUSERVO_UP_813,
        )

        # Load this mixin's pre-recorded DMA handle. The parent
        # PainterRampMixin's painter_dma already loads adiabatic_painter_ramp_on
        # via the cascade; all recording happens earlier in DMA_record_hook, so
        # loading from a separate subfragment (in any order) is fine.
        class AdiabaticCoolingDMAFrag(RedMOTCheckpoints):
            def build_fragment(self, adiabatic_cooling_ramp):
                self.adiabatic_cooling_ramp = adiabatic_cooling_ramp
                self.kernel_invariants = getattr(self, "kernel_invariants", set())
                self.kernel_invariants.add("adiabatic_cooling_ramp")

            @kernel
            def DMA_initialization_checkpoint(self):
                self.DMA_initialization_checkpoint_subfragments()
                self.adiabatic_cooling_ramp.precalculate_dma_handle()

        self.setattr_fragment(
            "adiabatic_cooling_dma",
            AdiabaticCoolingDMAFrag,
            adiabatic_cooling_ramp=self.adiabatic_cooling_ramp,
        )
        self.adiabatic_cooling_dma: AdiabaticCoolingDMAFrag

    @kernel
    def adiabatic_cooling_hook(self):
        self.painter_ramp_on()
        delay(DELAY_BETWEEN_RTIO_EVENTS)
        # Do the ramp
        self.adiabatic_cooling_ramp.do_phase()
