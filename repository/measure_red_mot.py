import logging

from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from artiq.experiment import TInt32
from artiq.experiment import TInt64
from artiq.experiment import TTuple
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64

from repository.lib import constants
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_3d_mot import Red3DMOTFrag

logger = logging.getLogger(__name__)


class _BroadbandBase(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot_controller", Blue3DMOTFrag)
        self.blue_mot_controller: Blue3DMOTFrag

        self.setattr_fragment("red_mot_controller", Red3DMOTFrag)
        self.red_mot_controller: Red3DMOTFrag

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        self.setattr_fragment(
            "camera_interface", DualCameraMeasurement, hardware_trigger=True
        )
        self.camera_interface: DualCameraMeasurement

        self.setattr_param(
            "red_broadband_time",
            FloatParam,
            "Time to spend in the broadband red mot",
            default=constants.RED_BROADBAND_TIME,
            unit="ms",
        )
        self.red_broadband_time: FloatParamHandle

        self.setattr_param(
            "red_broadband_gradient_current",
            FloatParam,
            "Current for gradient coils for broadband red MOT stage",
            default=constants.RED_BROADBAND_CURRENT,
            unit="A",
        )
        self.red_broadband_gradient_current: FloatParamHandle

        self.setattr_param(
            "red_broadband_suservo_multiple",
            FloatParam,
            "Multiple of nominal setpoint for suservo beams in broadband MOT",
            default=1.0,
            min=0.0,
        )
        self.red_broadband_suservo_multiple: FloatParamHandle

        # Ensure that both camera are on for the same length of time as the blue
        # fluorescence is pulsed
        self.setattr_param_rebind(
            "camera_exposure",
            self.camera_interface,
            "exposure_horiz",
            default=200e-6,
            description="Camera exposure and fluorescence pulse length",
        )
        self.camera_interface.bind_param(
            "exposure_vert",
            self.camera_exposure,
        )
        self.camera_exposure: FloatParamHandle

        # Expose various parameters for convenience
        self.setattr_param_rebind(
            "blue_loading_time",
            self.blue_mot_controller,
            "loading_time",
            description="Loading time in blue MOT",
        )
        self.setattr_param_rebind(
            "ramp_lower_detuning",
            self.red_mot_controller,
        )
        self.setattr_param_rebind(
            "ramp_upper_detuning",
            self.red_mot_controller,
        )
        self.setattr_param_rebind(
            "ramp_frequency",
            self.red_mot_controller,
        )
        self.setattr_param_rebind(
            "injection_aom_static_detuning",
            self.red_mot_controller,
        )

    @kernel
    def prepare_and_load_blue_mot(self):
        """
        Advances the timeline to the end of "blue loading time" and leave all
        the blue beams on
        """
        self.core.break_realtime()
        self.blue_mot_controller.init()
        self.red_mot_controller.init()

        # Clear the camera buffer in case we quit a previous sequence midway
        self.camera_interface.clear()  # FIXME: move to device_setup of dual camera interface

        self.core.break_realtime()

        # Load a blue mot
        self.blue_mot_controller.load_mot(clearout=True)

    @kernel
    def start_red_broadband(self):
        """
        Start sweeping red IJD, turn on the beams and drop the gradient

        Does not advance the timeline
        """

        self.red_mot_controller.set_mot_suservo_amplitude(
            self.red_broadband_suservo_multiple.get()
        )
        delay_mu(8)
        self.red_mot_controller.turn_on_mot_beams()
        delay_mu(8)
        self.red_mot_controller.start_ramping_red()
        delay_mu(8)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()  # ...but leave repumpers on
        delay_mu(8)
        self.chamber_2_field_setter.set_mot_gradient(
            self.red_broadband_gradient_current.get()
        )

        delay_mu(-4 * 8)

    @kernel
    def pulse_blue_and_image(self):
        """
        Flash on the blue light and pulse the camera triggers

        Advances the timeline by the duration of the imaging pulse and consumes
        a lane

        TODO: Use only one beam (or a dedicated beam)
        """
        with parallel:
            self.camera_interface.trigger()
            with sequential:
                self.blue_mot_controller.turn_on_3d_beams()
                delay(self.camera_exposure.get())
                self.blue_mot_controller.turn_off_3d_beams()


class _RampingPhase(Fragment):
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

    duration_default = 100e-3
    time_step_default = 100e-6
    start_detuning_default = 0.0
    end_detuning_default = 0.0
    start_gradient_default = 0.0
    end_gradient_default = 0.0
    start_suservo_nominal_multiple_default = 1.0
    end_suservo_nominal_multiple_default = 1.0

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
                "You must pass instances of Red3DMOTFrag and SetMagneticFields "
                "as keyword arguments to the build_fragment method of this subfragment. "
                "This is a hack - see inline comments."
            )

        self.red_mot_controller: Red3DMOTFrag = red_mot_controller
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
            "start_suservo_nominal_multiple",
            FloatParam,
            description="Initial suservo intensity as multiple of nominal intensity",
            default=self.start_suservo_nominal_multiple_default,
            min=0.0,
        )
        self.setattr_param(
            "end_suservo_nominal_multiple",
            FloatParam,
            description="Final suservo intensity as multiple of nominal intensity",
            default=self.end_suservo_nominal_multiple_default,
            min=0.0,
        )

        self.duration: FloatParamHandle
        self.time_step: FloatParamHandle
        self.start_detuning: FloatParamHandle
        self.end_detuning: FloatParamHandle
        self.start_gradient: FloatParamHandle
        self.end_gradient: FloatParamHandle
        self.start_suservo_nominal_multiple: FloatParamHandle
        self.end_suservo_nominal_multiple: FloatParamHandle

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
        suservo_step = (
            self.end_suservo_nominal_multiple.get()
            - self.start_suservo_nominal_multiple.get()
        ) / float(num_points - 1)

        # Record these ramping parameters into a DMA sequence
        with self.core_dma.record(self.fqn):
            # Initialise
            this_current = self.start_gradient.get()
            this_detuning = self.start_detuning.get()
            this_suservo_multiple = self.start_suservo_nominal_multiple.get()

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
                self.red_mot_controller.set_mot_suservo_amplitude(this_suservo_multiple)

                this_current += current_step
                this_detuning += detuning_step
                this_suservo_multiple += suservo_step

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


class NarrowRedCapturePhase(_RampingPhase):
    duration_default = 50e-3
    start_detuning_default = 150e3
    end_detuning_default = 50e3
    start_gradient_default = 5.0
    end_gradient_default = 1.0
    start_suservo_nominal_multiple_default = 1.0
    end_suservo_nominal_multiple_default = 0.1


class NarrowRedCompressionPhase(_RampingPhase):
    duration_default = 100e-3
    start_detuning_default = 50e3
    end_detuning_default = 10e3
    start_gradient_default = 1.0
    end_gradient_default = 1.0
    start_suservo_nominal_multiple_default = 0.1
    end_suservo_nominal_multiple_default = 0.02


class NarrowbandRedMOTFrag(_BroadbandBase):
    def build_fragment(self):
        super().build_fragment()

        # Add red phase fragments
        self.setattr_fragment(
            "narrow_red_capture_phase",
            NarrowRedCapturePhase,
            red_mot_controller=self.red_mot_controller,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_capture_phase: NarrowRedCapturePhase

        self.setattr_fragment(
            "narrow_red_compression_phase",
            NarrowRedCompressionPhase,
            red_mot_controller=self.red_mot_controller,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_compression_phase: NarrowRedCapturePhase

        self.setattr_param(
            "final_narrow_hold_time",
            FloatParam,
            "Time to hold in the final narrowband MOT before imaging",
            default=100e-3,
            unit="ms",
        )
        self.final_narrow_hold_time: FloatParamHandle

        self.setattr_param(
            "red_expansion_time",
            FloatParam,
            "Expansion time before imaging MOT",
            default=100e-6,
            min=0.0,
            unit="us",
        )
        self.red_expansion_time: FloatParamHandle

        self.setattr_device("ttl_camera_trigger_andor")
        self.ttl_camera_trigger_andor: TTLOut

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Preload phases' handles
        self.narrow_red_capture_phase.precalculate_dma_handle()
        self.narrow_red_compression_phase.precalculate_dma_handle()

    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()
        delay(self.red_broadband_time.get())

        self.red_mot_controller.stop_ramping_red()

        # This funny structure exists so that the imaging pulse happens after
        # the phase is completed, despite the phase ending with only a small
        # amount of slack and the shutter pre-opening requiring at least 20ms
        with parallel:
            with sequential:
                delay(
                    self.narrow_red_capture_phase.duration.get()
                    + self.narrow_red_compression_phase.duration.get()
                    + self.final_narrow_hold_time.get()
                    + self.red_expansion_time.get()
                )
                with parallel:
                    self.pulse_blue_and_image()
                    with sequential:
                        # FIXME: Remove this hack
                        self.ttl_camera_trigger_andor.pulse(1e-6)
                        # delay(10e-6)
                        # self.ttl_camera_trigger_andor.pulse(1e-6)
            with sequential:
                self.narrow_red_capture_phase.do_phase()
                self.narrow_red_compression_phase.do_phase()

                delay(self.final_narrow_hold_time.get())
                self.red_mot_controller.turn_off_mot_beams()
                delay(self.red_expansion_time.get())

        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


class MeasureBBRedMOTFrag(_BroadbandBase):
    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()

        # Note that red_broadband_time may be negative if we're imaging the blue MOT
        delay(self.red_broadband_time.get())

        with parallel:
            self.red_mot_controller.turn_off_mot_beams()
            self.pulse_blue_and_image()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


class MeasureBBRedMOTExpansionFrag(_BroadbandBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "red_expansion_time",
            FloatParam,
            "Expansion time before imaging MOT",
            default=100e-6,
            min=0.0,
            unit="us",
        )
        self.red_expansion_time: FloatParamHandle

    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()

        # Unlike for MeasureRedMOT, here we require that red_broadband_time be positive
        delay(self.red_broadband_time.get())

        self.red_mot_controller.turn_off_mot_beams()

        delay(self.red_expansion_time.get())

        self.pulse_blue_and_image()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


## % Commented out spectroscopy experiment - unusable until we have more red power
# class MeasureRedMOTSpectroscopy(_MeasureRedMOTBase):
#     def build_fragment(self):
#         super().build_fragment()

#         self.setattr_param(
#             "red_expansion_time",
#             FloatParam,
#             "Expansion time before pulsing 689",
#             default=10e-3,
#             unit="ms",
#         )
#         self.red_expansion_time: FloatParamHandle

#         self.setattr_param(
#             "spectroscopy_pulse_time",
#             FloatParam,
#             "Length of spectroscopy pulse",
#             default=50e-6,
#             unit="us",
#         )
#         self.spectroscopy_pulse_time: FloatParamHandle

#         self.setattr_param(
#             "spectroscopy_pulse_aom_frequency",
#             FloatParam,
#             "Frequency of AOM during spectroscopy pulse",
#             default=340e6,
#             unit="MHz",
#         )
#         self.spectroscopy_pulse_aom_frequency: FloatParamHandle

#     @kernel
#     def run_once(self):
#         if self.red_broadband_time.get() < 0:
#             raise RuntimeError("red_broadband_time must be greater than zero")

#         self.prepare_and_load_blue_mot()

#         self.start_red_loading()

#         # Unlike for MeasureRedMOT, here we require that red_broadband_time be positive
#         delay(self.red_broadband_time.get())

#         with parallel:
#             self.chamber_2_field_setter.set_mot_gradient(0.0)
#             self.red_mot_controller.turn_off_mot_beams(ignore_shutters=True)
#             self.red_mot_controller.stop_ramping_red(
#                 freq=self.spectroscopy_pulse_aom_frequency.get()
#             )

#         delay(self.red_expansion_time.get())

#         self.red_mot_controller.turn_on_mot_beams(ignore_shutters=True)
#         delay(self.spectroscopy_pulse_time.get())
#         self.red_mot_controller.turn_off_mot_beams()

#         with parallel:
#             self.camera_interface.trigger()
#             self.pulse_blue_for_image()

#         # Turn the fields back to defaults so eddy currents are gone by the next shot
#         self.blue_mot_controller.enable_mot_fields()

#         # End of RTIO sequencing. Now we are in real-time.

#         # Save the photos
#         self.core.wait_until_mu(now_mu())
#         self.camera_interface.save_data()


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureBBRedMOTExpansion = make_fragment_scan_exp(MeasureBBRedMOTExpansionFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(NarrowbandRedMOTFrag)
