import logging

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
    """Template fragment for a phase of the red mot

    Allows:
        * Ramping of beam intensitites
        * Ramping of gradient currents
        * Ramping of MOT beam detunings (via double-passed injection AOM)

    This fragment should be subclassed for each desired phase. Default settings
    for its parameters can be set by setting the appropriate class variable.

    Lookup of pre-recorded sequences is slow, but can be done before the
    sequence runs. To do this, use :meth:`~.precalculate_dma_handle` before
    calling :meth:`~.do_phase`.
    """

    time_step_default = 100e-6

    duration_default: float = None
    start_detuning_default: float = None
    end_detuning_default: float = None
    start_gradient_default: float = None
    end_gradient_default: float = None

    start_suservo_diagonal_multiple_default: float = None
    end_suservo_diagonal_multiple_default: float = None
    start_suservo_axialplus_multiple_default: float = None
    end_suservo_axialplus_multiple_default: float = None
    start_suservo_axialminus_multiple_default: float = None
    end_suservo_axialminus_multiple_default: float = None
    start_suservo_up_multiple_default: float = None
    end_suservo_up_multiple_default: float = None

    # TODO: Rewrite this Fragment so that all four red beams (including up) can
    # ramp independently. We'll need to keep the global multiple too, so that we
    # can ramp the two axial beams together. Richard suggests dumping global and
    # having an "axial" multiple instead - we could do this.

    def build_fragment(
        self, *args, red_mot_controller=None, chamber_2_field_setter=None
    ):
        # %% Fragments
        #
        # Unusually, here we pass fragments in via arguments to build_fragment
        # instead of recreasing them ourselves with self.setattr_fragment. This
        # is to prevent lots of device_setup calls being made for duplicate
        # subfragments, and to prevent proliferation of arguments in the ndscan
        # interface which don't need to be there (without having to do loads of
        # rebinding). Time will tell whether this is a good idea or not.
        #
        # Note from future Charles - this decision seems to cause ndscan to not
        # know how to display this fragment's parameters, treating them for some
        # reason as children of the SetMagneticFields object. So far, this seems
        # to be the only adverse effect. Still might be worth avoiding however.
        #
        # N.B.B. It also seems like this prevents me from overriding these
        # parameters. Dang, that's not usable therefore.
        #
        # N.B.B.B. This can be hacked... The problem comes from ndscan's attempt
        # to mangle arguments to fragments into its FQN. If I get around this by
        # passing the objects as keyword arguments instead of arguments then I
        # can avoid this. This is horribly ugly though, and is abusing a
        # "feature" of ndscan which they actively intend to fix at some point
        # according to comments.

        if red_mot_controller is None or chamber_2_field_setter is None:
            raise TypeError(
                "You must pass instances of RedBeamController and SetMagneticFields "
                "as keyword arguments to the build_fragment method of this subfragment. "
                "This is a hack - see inline comments."
            )

        for attr_name in [
            "start_suservo_diagonal_multiple_default",
            "end_suservo_diagonal_multiple_default",
            "start_suservo_axialplus_multiple_default",
            "end_suservo_axialplus_multiple_default",
            "start_suservo_axialminus_multiple_default",
            "end_suservo_axialminus_multiple_default",
            "start_suservo_up_multiple_default",
            "end_suservo_up_multiple_default",
            "duration_default",
            "start_detuning_default",
            "end_detuning_default",
            "start_gradient_default",
            "end_gradient_default",
        ]:
            if getattr(self, attr_name) is None:
                raise TypeError(
                    f'Attribute "{attr_name}" not defined'
                    "\n\n"
                    "You must subclass this type and define all the ramp parameters"
                )

        self.red_mot_controller: RedBeamController = red_mot_controller
        self.chamber_2_field_setter: SetMagneticFieldsQuick = chamber_2_field_setter
        self.gradient_current_setter = self.chamber_2_field_setter.current_setter_mot

        # %% Devices

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

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
            f"start_suservo_up_multiple_default",
            FloatParam,
            description="Initial suservo up intensity as multiple of nominal intensity",
            default=self.start_suservo_up_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            f"end_suservo_up_multiple_default",
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
        self.start_suservo_up_multiple_default: FloatParamHandle
        self.end_suservo_up_multiple_default: FloatParamHandle

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
            self.end_suservo_up_multiple_default.get()
            - self.start_suservo_up_multiple_default.get()
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
            this_suservo_up_multiple = self.start_suservo_up_multiple_default.get()

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
