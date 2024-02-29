from pyaion.fragments.suservo import LibSetSUServoStatic
import logging
from typing import *


from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import AD9910
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


logger = logging.getLogger(__name__)


class RampingRedPhase(Fragment):
    """
    Template fragment for a phase of the experiment which allows:

        * Ramping of beam intensitites
        * Ramping of gradient currents
        * Ramping of beam detunings

    This fragment should be subclassed for each desired phase. Default settings
    for its parameters can be set by setting the appropriate class variable.

    Note that this phase does not support zero-length lists of any object type.
    This is because handling these is hard in ARTIQ, since empty lists do not
    have an associated type and so kernel compilation breaks. Working around
    this is possible, but not done yet. Better to wait for the new compiler
    which solves this problem.

    Lookup of pre-recorded sequences is slow, but can be done before the
    sequence runs. To do this, use :meth:`~.precalculate_dma_handle` before
    calling :meth:`~.do_phase`.
    """

    time_step_default = 100e-6

    duration_default: float = None

    urukuls: List[str] = []
    default_urukul_nominal_frequencies: List[float] = []
    default_urukul_detunings_start: List[float] = []
    default_urukul_detunings_end: List[float] = []

    suservos: List[str] = []
    default_suservo_nominal_setpoints: List[float] = []
    default_suservo_setpoint_multiples_start: List[float] = []
    default_suservo_setpoint_multiples_end: List[float] = []

    current_controller = None  # FIXME: implement this somehow

    def validate_attributes(self):
        assert self.duration_default is not None

        # validate the class attributes to make sure this class was declared correctly
        assert len(self.urukuls) == len(set(self.urukuls)), TypeError(
            "self.urukuls contains duplicate entries"
        )
        assert len(self.default_urukul_nominal_frequencies) == len(
            self.urukuls
        ), TypeError(
            "default_urukul_nominal_frequencies must have same length as self.urukuls"
        )
        assert len(self.default_urukul_detunings_start) == len(self.urukuls), TypeError(
            "default_urukul_detunings_start must have same length as self.urukuls"
        )
        assert len(self.default_urukul_detunings_end) == len(self.urukuls), TypeError(
            "default_urukul_detunings_end must have same length as self.urukuls"
        )

        assert len(self.suservos) == len(set(self.suservos)), TypeError(
            "self.suservos_for_intensity contains duplicate entries"
        )
        assert len(self.default_suservo_setpoint_multiples_start) == len(
            self.suservos
        ), TypeError(
            "self.default_syservo_setpoints_start must have same length as self.suservos_for_intensity"
        )
        assert len(self.default_suservo_setpoint_multiples_end) == len(
            self.suservos
        ), TypeError(
            "self.default_syservo_setpoints_end must have same length as self.suservos_for_intensity"
        )

    def build_fragment(self, *args):
        self.validate_attributes()

        # %% Devices

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

        # %% SUServos

        self.suservo_setters_and_param_handles: List[
            Tuple[
                LibSetSUServoStatic,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        for suservo_name, setpoint_nominal, setpoint_start, setpoint_end in zip(
            self.suservos,
            self.default_suservo_nominal_setpoints,
            self.default_suservo_setpoint_multiples_start,
            self.default_suservo_setpoint_multiples_end,
        ):
            # For each requested SUServo, get a setter Fragment for it and
            # define parameters for the nominal setpoint, and the multiples of
            # that nominal value that this ramping phase should start and end
            # with. These will take default values defined by the class
            # attributes when a concrete instance of this class is created, but
            # the user will be able to override those value through normal
            # NDScan behaviour.
            setter = self.setattr_fragment(
                f"setter_{suservo_name}", LibSetSUServoStatic, suservo_name
            )

            setpoint_nominal_handle = self.setattr_param(
                f"setpoint_nominal_{suservo_name}",
                FloatParam,
                f"Nominal setpoint for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_nominal,
            )

            setpoint_start_handle = self.setattr_param(
                f"setpoint_multiple_start_{suservo_name}",
                FloatParam,
                f"Multiple of nominal setpoint at start of ramp for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_start,
            )

            setpoint_end_handle = self.setattr_param(
                f"setpoint_multiple_end_{suservo_name}",
                FloatParam,
                f"Multiple of nominal setpoint at end of ramp for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_end,
            )

            self.suservo_setters_and_param_handles.append(
                (
                    setter,
                    setpoint_nominal_handle,
                    setpoint_start_handle,
                    setpoint_end_handle,
                )
            )

        # %% Urukuls

        self.ad9910_channels_and_param_handles: List[
            Tuple[
                AD9910,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        for urukul_channel_name, frequency_nominal, detuning_start, detuning_end in zip(
            self.urukuls,
            self.default_urukul_nominal_frequencies,
            self.default_urukul_detunings_start,
            self.default_urukul_detunings_end,
        ):
            # For each requested SUServo, get a setter Fragment for it and
            # define parameters for the nominal setpoint, and the multiples of
            # that nominal value that this ramping phase should start and end
            # with. These will take default values defined by the class
            # attributes when a concrete instance of this class is created, but
            # the user will be able to override those value through normal
            # NDScan behaviour.
            channel: AD9910 = self.get_device(urukul_channel_name)

            nominal_freq_handle = self.setattr_param(
                f"frequency_nominal_{urukul_channel_name}",
                FloatParam,
                f"Nominal frequency for {urukul_channel_name}",
                min=0,
                unit="MHz",
                default=frequency_nominal,
            )

            detuning_start_handle = self.setattr_param(
                f"detuning_start_{urukul_channel_name}",
                FloatParam,
                f"Detuning from nominal frequency at start of ramp for {urukul_channel_name}",
                min=0,
                unit="MHz",
                default=detuning_start,
            )

            detuning_end_handle = self.setattr_param(
                f"detuning_end_{urukul_channel_name}",
                FloatParam,
                f"Detuning from nominal frequency at end of ramp for {urukul_channel_name}",
                min=0,
                unit="MHz",
                default=detuning_end,
            )

            self.ad9910_channels_and_param_handles.append(
                (
                    channel,
                    nominal_freq_handle,
                    detuning_start_handle,
                    detuning_end_handle,
                )
            )

        # %% Other parameters

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

        self.duration: FloatParamHandle
        self.time_step: FloatParamHandle

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.dma_handle = (int32(0), int64(0), int32(0), False)
        self.dma_handle_valid = False

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
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

        # FIXME: Compute step sizes for the gradient coils...
        # current_step = (self.end_gradient.get() - self.start_gradient.get()) / float(
        #     num_points - 1
        # )

        # ...the detunings...
        for (
            _,
            nom_setpoint_handle,
            start_multiple_handle,
            end_multiple_handle,
        ) in self.suservo_setters_and_param_handles:
            detuning_step = (
                self.end_detuning.get() - self.start_detuning.get()
            ) / float(num_points - 1)

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
