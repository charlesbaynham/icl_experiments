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
from artiq.experiment import TList
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.fluorescence_pulse import ImagingFluorescencePulse
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.ramping_phase import RampingRedPhase
from repository.lib.fragments.ramping_phase_alt import GeneralRampingPhase
from repository.lib.fragments.red_beam_controller import RedBeamController

logger = logging.getLogger(__name__)

# Time to allow for ramp SPI transaction
RAMP_SPI_DELAY = 10e-6


class NarrowRedCapturePhase(GeneralRampingPhase):
    duration_default = 50e-3

    urukuls = ["urukul9910_aom_doublepass_689_red_injection"]
    default_urukul_detunings_start = [150e3]
    default_urukul_detunings_end = [50e3]
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]

    suservos = [
        "suservo_aom_singlepass_689_red_mot_sigmaplus",
        "suservo_aom_singlepass_689_red_mot_sigmaminus",
        "suservo_aom_singlepass_689_red_mot_diagonal",
        "suservo_aom_singlepass_689_up",
    ]
    default_suservo_setpoint_multiples_start = [1.0, 1.0, 1.0, 0.0]
    default_suservo_setpoint_multiples_end = [0.1, 0.1, 0.1, 0.0]

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * 4

    # The general ramp here ramps the chamber 2 MOT coils in amps
    general_setter_default_starts = [5.0]
    general_setter_default_ends = [1.0]
    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(
        self, *args, chamber_2_field_setter: SetMagneticFieldsQuick = None
    ):
        if chamber_2_field_setter is None:
            raise TypeError("You must pass chamber_2_field_setter into build_fragment")
        self.field_setter = chamber_2_field_setter

        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(*args, general_setter=self.set_fields)

    @kernel
    def set_fields(self, vals: TList(TFloat)):
        self.field_setter.set_mot_gradient(vals[0])


class NarrowRedCompressionPhase(RampingRedPhase):
    duration_default = 100e-3
    start_detuning_default = 50e3
    end_detuning_default = 10e3
    start_gradient_default = 1.0
    end_gradient_default = 1.0

    start_suservo_diagonal_multiple_default = 0.1
    end_suservo_diagonal_multiple_default = 0.02
    start_suservo_axialplus_multiple_default = 0.1
    end_suservo_axialplus_multiple_default = 0.02
    start_suservo_axialminus_multiple_default = 0.1
    end_suservo_axialminus_multiple_default = 0.02
    start_suservo_up_multiple_default = 0.0
    end_suservo_up_multiple_default = 0.0


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
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_capture_phase: NarrowRedCapturePhase
        # Bind the default frequency in this phase to this Fragment's version of the same
        self.narrow_red_capture_phase.bind_ad9910_frequency_params(
            [self.injection_aom_static_detuning]
        )
        # For the SUServo setpoints, bind these to the FloatParameters defined
        # by the DefaultBeamSetter so that this is the only place which defines
        # SUServo setpoints
        info_and_handles = list(
            self.red_beam_controller.all_beam_default_setter.get_setpoints_and_beaminfo_dict().values()
        )
        handles = []
        for suservo_device_name in self.narrow_red_capture_phase.suservos:
            for info, handle in info_and_handles:
                if info.suservo_device == suservo_device_name:
                    handles.append(handle)
                    break
            else:
                raise ValueError(
                    f"SUServo {suservo_device_name} not found in all_beam_default_setter"
                )
        self.narrow_red_capture_phase.bind_suservo_setpoint_params(handles)

        self.setattr_fragment(
            "narrow_red_compression_phase",
            NarrowRedCompressionPhase,
            red_mot_controller=self.red_beam_controller,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.narrow_red_compression_phase: NarrowRedCompressionPhase

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
        with parallel:
            self.red_beam_controller.stop_ramping_red()
            delay(RAMP_SPI_DELAY)  # Constant delay > SPI write duration
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
        self.red_beam_controller.stop_ramping_red()
        self.transition_broadband_to_narrowband()

    @kernel
    def get_total_narrowband_duration(self) -> TFloat:
        "Get the duration of all the narrowband stages"
        return (
            self.narrow_red_capture_phase.duration.get()
            + RAMP_SPI_DELAY
            + self.narrow_red_compression_phase.duration.get()
            + self.final_narrow_hold_time.get()
        )
