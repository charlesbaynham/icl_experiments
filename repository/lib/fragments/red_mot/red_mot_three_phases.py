import logging

from artiq.compiler.builtins import TFloat
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import parallel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_mot.red_beam_controller import RedBeamController
from repository.lib.fragments.red_mot.red_mot_phases import (
    BroadbandRedPhaseWithBiasRamp,
)
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCapturePhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCompressionPhase

logger = logging.getLogger(__name__)

# Time to allow for ramp SPI transaction
RAMP_SPI_DELAY = 10e-6


class RedMOTThreePhaseFrag(Fragment):
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

        self.setattr_device("ttl_shutter_repump_679")
        self.ttl_shutter_repump_679: TTLOut

        self.setattr_param(
            "disable_679_during_narrowband",
            BoolParam,
            description="Disable 679 during narrowband MOT",
            default=False,
        )
        self.disable_679_during_narrowband: BoolParamHandle

        # %% Narrowband stuff

        # Add red phase fragments

        self.setattr_fragment(
            "broadband_red_phase",
            BroadbandRedPhaseWithBiasRamp,
        )
        self.broadband_red_phase: BroadbandRedPhaseWithBiasRamp

        self.setattr_fragment(
            "narrow_red_capture_phase",
            NarrowRedCapturePhase,
        )
        self.narrow_red_capture_phase: NarrowRedCapturePhase

        self.setattr_fragment(
            "narrow_red_compression_phase",
            NarrowRedCompressionPhase,
        )
        self.narrow_red_compression_phase: NarrowRedCompressionPhase

        # Bind the default frequency in the phases to this Fragment's version of
        # the same (N.B. don't bother for the Broadband phase since it has no Urukul)
        self.narrow_red_capture_phase.bind_ad9910_frequency_params(
            [self.injection_aom_static_frequency]
        )
        self.narrow_red_compression_phase.bind_ad9910_frequency_params(
            [self.injection_aom_static_frequency]
        )

        # Bind the SUServo setpoint parameters to those defined in the red default beam setter
        self.broadband_red_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            self.red_beam_controller.all_beam_default_setter
        )
        self.narrow_red_capture_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            self.red_beam_controller.all_beam_default_setter
        )
        self.narrow_red_compression_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            self.red_beam_controller.all_beam_default_setter
        )

        for axis in ["x", "y", "z"]:
            self.setattr_param(
                f"narrowband_bias_{axis}",
                FloatParam,
                f"Bias current for narrowband MOT - {axis.upper()}",
                default=getattr(constants, f"RED_NARROWBAND_BIAS_FIELD_{axis.upper()}"),
                unit="A",
                min=-5,
                max=5,
            )
        self.narrowband_bias_x: FloatParamHandle
        self.narrowband_bias_y: FloatParamHandle
        self.narrowband_bias_z: FloatParamHandle

        self.setattr_param(
            "final_narrow_hold_time",
            FloatParam,
            "Time to hold in the final narrowband MOT before imaging",
            default=constants.RED_MOT_FINAL_HOLD_TIME,
            unit="ms",
        )
        self.final_narrow_hold_time: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Setup beam state
        self.core.break_realtime()
        delay(1e-3)
        self.red_beam_controller.init()

    @kernel
    def prepare_for_broadband_phase(self):
        """
        Start sweeping red IJD and turn on the beams in preparation for the
        broadband phase

        Does not turn off blue beams - you should do this elsewhere.

        Advances the timeline by the duration of SPI writes. The timeline is
        left pointing at the moment that the beams turn on. Writes into the past
        for shutter opening.
        """

        self.red_beam_controller.start_ramping_red()
        delay_mu(int64(self.core.ref_multiplier))
        self.red_beam_controller.turn_on_mot_beams()

    @kernel
    def terminate_broadband_mot(self):
        """
        Disable the broadband MOT, in preparation for a narrowband MOT

        Advances the timeline by the duration of a few SPI writes.
        """
        # Delay by at least RAMP_SPI_DELAY > SPI write duration. This is so that
        # get_total_narrowband_duration can predict the total duration of these
        # stages accurately
        with parallel:
            self.red_beam_controller.stop_ramping_red()
            delay(RAMP_SPI_DELAY)

        if self.disable_679_during_narrowband.get():
            self.ttl_shutter_repump_679.off()

    @kernel
    def do_narrowband_red_mot(self):
        """
        Perform the narrowband red mot phases

        Advances the timeline by the duration of the narrowband red MOT + hold time
        """
        self.narrow_red_capture_phase.do_phase()
        self.narrow_red_compression_phase.do_phase()

        delay(self.final_narrow_hold_time.get())

    @kernel
    def get_total_narrowband_duration(self) -> TFloat:
        "Get the duration of all the narrowband stages"
        return (
            RAMP_SPI_DELAY
            + self.narrow_red_capture_phase.duration.get()
            + self.narrow_red_compression_phase.duration.get()
            + self.final_narrow_hold_time.get()
        )
