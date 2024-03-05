import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import parallel
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_mot.red_beam_controller import RedBeamController
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCapturePhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCompressionPhase

logger = logging.getLogger(__name__)

# Time to allow for ramp SPI transaction
RAMP_SPI_DELAY = 10e-6


class NarrowbandRedMOTFrag(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("red_beam_controller", RedBeamController)
        self.red_beam_controller: RedBeamController

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

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

        self.setattr_param_rebind(
            "ramp_lower_detuning",
            self.red_beam_controller,
        )
        self.setattr_param_rebind(
            "ramp_upper_detuning",
            self.red_beam_controller,
        )
        self.setattr_param_rebind(
            "ramp_frequency",
            self.red_beam_controller,
        )
        self.setattr_param_rebind(
            "injection_aom_static_frequency",
            self.red_beam_controller,
        )
        self.injection_aom_static_frequency: FloatParamHandle

        # %% Narrowband stuff

        # Add red phase fragments
        self.setattr_fragment(
            "narrow_red_capture_phase",
            NarrowRedCapturePhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_capture_phase: NarrowRedCapturePhase
        self.setattr_fragment(
            "narrow_red_compression_phase",
            NarrowRedCompressionPhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_compression_phase: NarrowRedCompressionPhase

        # Bind the default frequency in the phases to this Fragment's version of
        # the same
        self.narrow_red_capture_phase.bind_ad9910_frequency_params(
            [self.injection_aom_static_frequency]
        )
        self.narrow_red_compression_phase.bind_ad9910_frequency_params(
            [self.injection_aom_static_frequency]
        )

        # Bind the SUServo setpoint parameters to those defined in the red default beam setter
        self.narrow_red_capture_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            self.red_beam_controller.all_beam_default_setter
        )
        self.narrow_red_compression_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            self.red_beam_controller.all_beam_default_setter
        )

        self.setattr_param(
            "final_narrow_hold_time",
            FloatParam,
            "Time to hold in the final narrowband MOT before imaging",
            default=100e-3,
            unit="ms",
        )
        self.final_narrow_hold_time: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Preload phases' handles
        self.narrow_red_capture_phase.precalculate_dma_handle()
        self.narrow_red_compression_phase.precalculate_dma_handle()

        # Setup beam state
        self.core.break_realtime()
        self.red_beam_controller.init()

    @kernel
    def start_red_broadband(self):
        """
        Start sweeping red IJD, turn on the beams and drop the gradient

        Does not turn off blue beams - you should do this elsewhere.

        Does not advance the timeline
        """

        self.red_beam_controller.set_mot_suservo_amplitude_global(
            self.red_broadband_suservo_multiple.get()
        )
        delay_mu(8)
        self.red_beam_controller.turn_on_mot_beams()
        delay_mu(8)
        self.red_beam_controller.start_ramping_red()
        delay_mu(8)
        self.chamber_2_field_setter.set_mot_gradient(
            self.red_broadband_gradient_current.get()
        )

        delay_mu(-4 * 8)

    @kernel
    def transition_broadband_to_narrowband(self):
        """
        Perform all the ramping phases that occurs after the broadband red MOT
        to create a narrowband MOT.

        Advances the timeline by the duration of the phases + the final hold
        time.
        """
        # Delay by at least RAMP_SPI_DELAY > SPI write duration. This is so that
        # get_total_narrowband_duration can predict the total duration of these
        # stages accurately
        with parallel:
            self.red_beam_controller.stop_ramping_red()
            delay(RAMP_SPI_DELAY)

        self.narrow_red_capture_phase.do_phase()
        self.narrow_red_compression_phase.do_phase()

        delay(self.final_narrow_hold_time.get())

    @kernel
    def load_narrowband_mot_from_blue_mot(self):
        """
        From a blue MOT, load a narrowband MOT

        Does not turn off the blue beams - you must do this elsewhere

        Advances the timeline by the total duration of all ramping phases and
        hold times configured in this fragment
        """
        self.start_red_broadband()
        delay(self.red_broadband_time.get())
        self.transition_broadband_to_narrowband()

    @kernel
    def get_total_narrowband_duration(self) -> TFloat:
        "Get the duration of all the narrowband stages"
        return (
            RAMP_SPI_DELAY
            + self.narrow_red_capture_phase.duration.get()
            + self.narrow_red_compression_phase.duration.get()
            + self.final_narrow_hold_time.get()
        )
