import logging
from typing import *

from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.experiment import at_mu
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64

from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_beam_controller import RedBeamController

logger = logging.getLogger(__name__)


class RampingRedPhase(Fragment):
    """
    Template fragment for a phase of the experiment which allows:

        * Ramping of beam intensitites
        * Ramping of gradient currents
        * Ramping of beam detunings 

    This fragment should be subclassed for each desired phase. Default settings
    for its parameters can be set by setting the appropriate class variable.

    Lookup of pre-recorded sequences is slow, but can be done before the
    sequence runs. To do this, use :meth:`~.precalculate_dma_handle` before
    calling :meth:`~.do_phase`.
    """

    time_step_default = 100e-6

    duration_default: float = None

    urukuls:List[str] = []
    default_urukul_nominal_frequencies :List[float] = []
    default_urukul_detunings_start: List[float] = []
    default_urukul_detunings_end: List[float] = []

    suservos_for_intensity:List[str] = []
    default_suservo_nominal_setpoints:List[float] = []
    # FIXME: Rename these when I have a proper IDE available... I'm using multiples instead of absolutes
    default_suservo_setpoints_start: List[float] = []
    default_suservo_setpoints_end: List[float] = []

    current_controller = None  # FIXME: implement this somehow

    def validate_attributes(self):
        assert duration_default is not None

        # validate the class attributes to make sure this class was declared correctly
        assert len(self.urukuls) == len(set(self.urukuls)), TypeError("self.urukuls contains duplicate entries")
        assert len(self.default_urukul_nominal_frequencies) == len(self.urukuls), TypeError("default_urukul_nominal_frequencies must have same length as self.urukuls")
        assert len(self.default_urukul_detunings_start) == len(self.urukuls), TypeError("default_urukul_detunings_start must have same length as self.urukuls")
        assert len(self.default_urukul_detunings_end) == len(self.urukuls), TypeError("default_urukul_detunings_end must have same length as self.urukuls")

        assert len(self.suservos_for_intensity) == len(set(self.suservos_for_intensity)), TypeError("self.suservos_for_intensity contains duplicate entries")
        assert len(self.default_suservo_setpoints_start) == len(self.suservos_for_intensity), TypeError("self.default_syservo_setpoints_start must have same length as self.suservos_for_intensity")
        assert len(self.default_suservo_setpoints_end) == len(self.suservos_for_intensity), TypeError("self.default_syservo_setpoints_end must have same length as self.suservos_for_intensity")


    def build_fragment(
        self, *args
    ):
        self.validate_attributes()

        # %% Devices

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

        # SUServos
        for suservo_device in self.suservos_for_intensity:
            setter = self.setattr_fragment(
              f"setter_{suservo_device}", LibSetSUServoStatic, suservo_device
            )

            setpoint_start_handle = self.setattr_param(
                f"setpoint_start_{beam_info.name}",
                FloatParam,
                f"SUServo setpoint for {beam_info.name}",
                min=0,
                unit="V",
                default=beam_info.setpoint,
            )

            self.suservo_setters_and_info.append(
                (setter, setpoint_handle, bool(beam_info.shutter_device))
            )


        

        # %% Parameters

        self.setattr_param(
            "duration",
            FloatParam,
            "Duration of phase",
            default=self.duration_default,
            min=0.0,
            unit="ms",
        )
        self.setattr_param(
            "time_step",
            FloatParam,
            "Gap between steps",
            default=self.time_step_default,
            min=0.0,
            unit="us",
        )
        self.setattr_param(
            "start_detuning",
            FloatParam,
            description="Initial detuning of red beams",
            default=self.start_detuning_default,
            unit="MHz",
        )
        self.setattr_param(
            "end_detuning",
            FloatParam,
            description="Final detuning of red beams",
            default=self.end_detuning_default,
            unit="MHz",
        )

        self.setattr_param(
            "start_gradient",
            FloatParam,
            description="Initial gradient current",
            default=self.start_gradient_default,
            min=0.0,
            unit="A",
        )
        self.setattr_param(
            "end_gradient",
            FloatParam,
            description="Final gradient current",
            default=self.end_gradient_default,
            min=0.0,
            unit="A",
        )

        self.setattr_param(
            f"start_suservo_diagonal_multiple",
            FloatParam,
            description="Initial suservo diagonal intensity as multiple of nominal intensity",
            default=self.start_suservo_diagonal_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            f"end_suservo_diagonal_multiple",
            FloatParam,
            description="Final suservo diagonal intensity as multiple of nominal intensity",
            default=self.end_suservo_diagonal_multiple_default,
            min=0.0,
        )

        self.setattr_param(
            f"start_suservo_axialplus_multiple",
            FloatParam,
            description="Initial suservo axialplus intensity as multiple of nominal intensity",
            default=self.start_suservo_axialplus_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            f"end_suservo_axialplus_multiple",
            FloatParam,
            description="Final suservo axialplus intensity as multiple of nominal intensity",
            default=self.end_suservo_axialplus_multiple_default,
            min=0.0,
        )

        self.setattr_param(
            f"start_suservo_axialminus_multiple",
            FloatParam,
            description="Initial suservo axialminus intensity as multiple of nominal intensity",
            default=self.start_suservo_axialminus_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            f"end_suservo_axialminus_multiple",
            FloatParam,
            description="Final suservo axialminus intensity as multiple of nominal intensity",
            default=self.end_suservo_axialminus_multiple_default,
            min=0.0,
        )

        self.setattr_param(
            f"start_suservo_up_multiple",
            FloatParam,
            description="Initial suservo up intensity as multiple of nominal intensity",
            default=self.start_suservo_up_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            f"end_suservo_up_multiple",
            FloatParam,
            description="Final suservo up intensity as multiple of nominal intensity",
            default=self.end_suservo_up_multiple_default,
            min=0.0,
        )

        self.duration: FloatParamHandle
        self.time_step: FloatParamHandle
        self.start_detuning: FloatParamHandle
        self.end_detuning: FloatParamHandle
        self.start_gradient: FloatParamHandle
        self.end_gradient: FloatParamHandle
        self.start_suservo_diagonal_multiple: FloatParamHandle
        self.end_suservo_diagonal_multiple: FloatParamHandle
        self.start_suservo_axialplus_multiple: FloatParamHandle
        self.end_suservo_axialplus_multiple: FloatParamHandle
        self.start_suservo_axialminus_multiple: FloatParamHandle
        self.end_suservo_axialminus_multiple: FloatParamHandle
        self.start_suservo_up_multiple: FloatParamHandle
        self.end_suservo_up_multiple: FloatParamHandle

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.dma_handle = (int32(0), int64(0), int32(0), False)
        self.dma_handle_valid = False

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "red_mot_controller",
            "chamber_2_field_setter",
            "gradient_current_setter",
        }

    @kernel
    def device_setup(self):
        """
        Records the ramps to DMA.
        Write events are staggered by 8 ns (self.core.ref_multiplier) to use
        only one lane
        """
        self.device_setup_subfragments()

        # Compute grid for writes
        num_points = 1 + int(self.duration.get() // self.time_step.get())
        time_step_mu = self.core.seconds_to_mu(self.duration.get() / float(num_points))

        # Compute step sizes for the gradient coils...
        current_step = (self.end_gradient.get() - self.start_gradient.get()) / float(
            num_points - 1
        )

        # ...the detunings...
        detuning_step = (self.end_detuning.get() - self.start_detuning.get()) / float(
            num_points - 1
        )

        # ...and the SUServo amplitudes
        suservo_step_diagonal = (
            self.end_suservo_diagonal_multiple.get()
            - self.start_suservo_diagonal_multiple.get()
        ) / float(num_points - 1)
        suservo_step_axialplus = (
            self.end_suservo_axialplus_multiple.get()
            - self.start_suservo_axialplus_multiple.get()
        ) / float(num_points - 1)
        suservo_step_axialminus = (
            self.end_suservo_axialminus_multiple.get()
            - self.start_suservo_axialminus_multiple.get()
        ) / float(num_points - 1)
        suservo_step_up = (
            self.end_suservo_up_multiple.get() - self.start_suservo_up_multiple.get()
        ) / float(num_points - 1)

        # Record these ramping parameters into a DMA sequence
        with self.core_dma.record(self.fqn):
            # Initialise
            this_current = self.start_gradient.get()
            this_detuning = self.start_detuning.get()
            this_suservo_diagonal_multiple = self.start_suservo_diagonal_multiple.get()
            this_suservo_axialplus_multiple = (
                self.start_suservo_axialplus_multiple.get()
            )
            this_suservo_axialminus_multiple = (
                self.start_suservo_axialminus_multiple.get()
            )
            this_suservo_up_multiple = self.start_suservo_up_multiple.get()

            t_this_cycle_mu = now_mu()

            # Play the ramp
            for _ in range(num_points):
                at_mu(t_this_cycle_mu)

                self.gradient_current_setter.set_currents([this_current])
                delay_mu(
                    int64(self.core.ref_multiplier)
                )  # Try to avoid using multiple lanes
                self.red_mot_controller.set_mot_detuning(this_detuning)
                delay_mu(int64(self.core.ref_multiplier))
                self.red_mot_controller.set_mot_suservo_amplitude_individual(
                    amplitude_red_diagonal=this_suservo_diagonal_multiple,
                    amplitude_red_axialplus=this_suservo_axialplus_multiple,
                    amplitude_red_axialminus=this_suservo_axialminus_multiple,
                    amplitude_red_up=this_suservo_up_multiple,
                )

                this_current += current_step
                this_detuning += detuning_step
                this_suservo_diagonal_multiple += suservo_step_diagonal
                this_suservo_axialplus_multiple += suservo_step_axialplus
                this_suservo_axialminus_multiple += suservo_step_axialminus
                this_suservo_up_multiple += suservo_step_up

                t_this_cycle_mu += time_step_mu

        if self.debug_enabled:
            logger.info('Saving dma trace as "%s"', self.fqn)

    @kernel
    def precalculate_dma_handle(self):
        self.dma_handle = self.core_dma.get_handle(self.fqn)
        self.dma_handle_valid = True

    @kernel
    def do_phase(self):
        """
        Perform the ramps (or steps) associated with this phase, as configured
        by the parameters

        Advances the timeline to the end of the ramp
        """

        t_end_mu = now_mu() + self.core.seconds_to_mu(self.duration.get())

        # It's nicer to use handles here instead of string lookup.
        # Unfortunately, the DMA handle changes whenever another DMA sequence is
        # recorded, so this Fragment can't handle the case that another Fragment
        # uses DMA after this Fragment's device_setup completes. If the user
        # needs the performance of pre-pre-computed handles, they should call
        # precalculate_dma_handle before this method.
        if self.dma_handle_valid:
            self.core_dma.playback_handle(self.dma_handle)
        else:
            self.core_dma.playback(self.fqn)

        # Ensure that the timeline points to the end of the phase, not just the
        # final RTIO point
        at_mu(t_end_mu)
