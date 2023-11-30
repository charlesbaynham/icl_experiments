import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.fluorescence_pulse import FluorescencePulse
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.ramping_phase import RampingRedPhase
from repository.lib.fragments.red_beam_controller import RedBeamController

logger = logging.getLogger(__name__)


class NarrowRedCapturePhase(RampingRedPhase):
    duration_default = 50e-3
    start_detuning_default = 150e3
    end_detuning_default = 50e3
    start_gradient_default = 5.0
    end_gradient_default = 1.0
    start_suservo_nominal_multiple_default = 1.0
    end_suservo_nominal_multiple_default = 0.1


class NarrowRedCompressionPhase(RampingRedPhase):
    duration_default = 100e-3
    start_detuning_default = 50e3
    end_detuning_default = 10e3
    start_gradient_default = 1.0
    end_gradient_default = 1.0
    start_suservo_nominal_multiple_default = 0.1
    end_suservo_nominal_multiple_default = 0.02


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
            "injection_aom_static_detuning",
            self.red_beam_controller,
        )
        self.injection_aom_static_detuning: FloatParamHandle

        # %% Narrowband stuff

        # Add red phase fragments
        self.setattr_fragment(
            "narrow_red_capture_phase",
            NarrowRedCapturePhase,
            red_mot_controller=self.red_beam_controller,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_capture_phase: NarrowRedCapturePhase

        self.setattr_fragment(
            "narrow_red_compression_phase",
            NarrowRedCompressionPhase,
            red_mot_controller=self.red_beam_controller,
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

        self.red_beam_controller.set_mot_suservo_amplitude(
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
        self.red_beam_controller.stop_ramping_red()
        self.narrow_red_capture_phase.do_phase()
        self.narrow_red_compression_phase.do_phase()

        delay(self.final_narrow_hold_time.get())

    # @kernel
    # def pulse_blue_and_image(self):
    #     """
    #     Flash on the blue light and pulse the camera triggers

    #     Advances the timeline by the duration of the imaging pulse and consumes
    #     a lane

    #     TODO: Use only one beam (or a dedicated beam)
    #     """
    #     with parallel:
    #         self.camera_interface.trigger()
    #         with sequential:
    #             self.blue_mot_controller.turn_on_3d_beams()
    #             delay(self.camera_exposure.get())
    #             self.blue_mot_controller.turn_off_3d_beams()

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
        self.red_beam_controller.stop_ramping_red()
        self.transition_broadband_to_narrowband()

    @kernel
    def get_total_narrowband_duration(self) -> TFloat:
        "Get the duration of all the narrowband stages"
        return (
            self.narrow_red_capture_phase.duration.get()
            + self.narrow_red_compression_phase.duration.get()
            + self.final_narrow_hold_time.get()
        )

    # @kernel
    # def run_once(self):
    #     self.prepare_and_load_blue_mot()

    #     self.load_narrowband_mot_from_blue_mot()

    #     # This funny structure exists so that the imaging pulse happens after
    #     # the phase is completed, despite the phase ending with only a small
    #     # amount of slack and the shutter pre-opening requiring at least 20ms
    #     with parallel:
    #         with sequential:
    #             delay(
    #                 self.get_total_narrowband_duration() + self.red_expansion_time.get()
    #             )
    #             with parallel:
    #                 self.pulse_blue_and_image()
    #                 with sequential:
    #                     # FIXME: Remove this hack
    #                     self.ttl_camera_trigger_andor.pulse(1e-6)
    #                     delay(10e-6)
    #                     self.ttl_camera_trigger_andor.pulse(1e-6)

    #     self.core.wait_until_mu(now_mu())
    #     self.camera_interface.save_data()
