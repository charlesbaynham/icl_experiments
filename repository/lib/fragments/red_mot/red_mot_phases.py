"""
Define the phases available for making red MOTs

This module currently breaks the rule about only storing physics-determined
numbers in `constants.py`.
"""
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import TFloat
from artiq.experiment import TList

from repository.lib import constants
from repository.lib.fragments.beams.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.ramping_phase import GeneralRampingPhase


class RedRampingPhaseWithFieldsAndSUServoBindings(GeneralRampingPhase):
    """
    Subclass the GeneralRampingPhase specifically for red MOTs. I.e.:

    * Specify the 689 double-passed AOM as an Urukul to ramp
    * Control the 4 red beams
    * Add control of the B fields in chamber 2
    """

    urukuls = ["urukul9910_aom_doublepass_689_red_injection"]
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = [
        "suservo_aom_singlepass_689_red_mot_sigmaplus",
        "suservo_aom_singlepass_689_red_mot_sigmaminus",
        "suservo_aom_singlepass_689_red_mot_diagonal",
        "suservo_aom_singlepass_689_up",
    ]

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * 4

    # The general ramp here ramps the chamber 2 MOT coils in amps
    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(self, chamber_2_field_setter: SetMagneticFieldsQuick = None):
        if chamber_2_field_setter is None:
            raise TypeError("You must pass chamber_2_field_setter into build_fragment")
        self.field_setter = chamber_2_field_setter

        return super().build_fragment()

    @kernel
    def general_setter(self, vals: TList(TFloat)):
        self.field_setter.set_mot_gradient(vals[0])

    @host_only
    def bind_suservo_setpoint_params_to_default_beam_setter(
        self, beam_setter: SetBeamsToDefaults
    ):
        """
        Use the GeneralRampingPhase's :meth:`~.bind_suservo_setpoint_params`
        method to bind all this GeneralRampingPhase's suservo setpoint
        parameters to those defined by a `SetBeamsToDefaults`.

        This is a slightly ugly thing to do since it couples two objects that
        shouldn't need to know about each other, i.e. the GeneralRampingPhase
        whose responisibility is to ramp SUServo setpoints (and other things)
        and the SetBeamsToDefaults object whose responsibility it is to set up
        SUServos with their default settings.

        However, by doing it like this there is a single place in the ndscan
        parameter tree where all the setpoints for the red beams are defined,
        i.e. in the SetBeamsToDefaults owned by the red_beam_controller. This
        method glues those two objects together, but I'm adding it here in the
        red_mot module since I'd like to keep the GeneralRampingPhase code
        decoupled from the beam_setter module.
        """
        # For the SUServo setpoints, bind these to the FloatParameters defined
        # by the DefaultBeamSetter so that this is the only place which defines
        # SUServo setpoints
        info_and_handles = list(beam_setter.get_setpoints_and_beaminfo_dict().values())
        handles = []
        for suservo_device_name in self.suservos:
            for info, handle in info_and_handles:
                if info.suservo_device == suservo_device_name:
                    handles.append(handle)
                    break
            else:
                raise ValueError(
                    f"SUServo {suservo_device_name} not found in all_beam_default_setter"
                )
        self.bind_suservo_setpoint_params(handles)


class BroadbandRedPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    """
    Note that this phase does not start / stop the modulation of the IJD AOM.
    You must do this elsewhere
    """

    duration_default = constants.RED_BROADBAND_TIME
    time_step_default = (
        20e-3  # TODO: fix this by changing the ordering of the camera shutter queueing
    )

    # For the broadband stage we don't want control over the Urukul since the
    # frequency is controlled by the fast ramp rate. The parameters controlling
    # that ramp rate are not currently rampable - we could add this if required
    # but it's getting conceptually complicated
    urukuls = []
    default_urukul_amplitudes_start = []
    default_urukul_amplitudes_end = []
    default_urukul_detunings_start = []
    default_urukul_detunings_end = []
    default_urukul_nominal_frequencies = []

    # Order:
    # "suservo_aom_singlepass_689_red_mot_sigmaplus",
    # "suservo_aom_singlepass_689_red_mot_sigmaminus",
    # "suservo_aom_singlepass_689_red_mot_diagonal",
    # "suservo_aom_singlepass_689_up",
    default_suservo_setpoint_multiples_start = [2.2, 2.2, 2.5, 0.0]
    default_suservo_setpoint_multiples_end = [2.2, 2.2, 2.5, 0.0]

    # Chamber 2 MOT coils in amps
    general_setter_default_starts = [9.0]
    general_setter_default_ends = [9.0]


class NarrowRedCapturePhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = 100e-3

    default_urukul_detunings_start = [150e3]
    default_urukul_detunings_end = [50e3]

    # Order:
    # "suservo_aom_singlepass_689_red_mot_sigmaplus",
    # "suservo_aom_singlepass_689_red_mot_sigmaminus",
    # "suservo_aom_singlepass_689_red_mot_diagonal",
    # "suservo_aom_singlepass_689_up",
    default_suservo_setpoint_multiples_start = [0.55, 0.35, 0.6, 0.0]
    default_suservo_setpoint_multiples_end = [0.1, 0.1, 0.1, 0.0]

    # Chamber 2 MOT coils in amps
    general_setter_default_starts = [3.0]
    general_setter_default_ends = [1.0]


class NarrowRedCompressionPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = 100e-3

    default_urukul_detunings_start = [50e3]
    default_urukul_detunings_end = [10e3]

    # Chamber 2 MOT coils in amps
    general_setter_default_starts = [1.0]
    general_setter_default_ends = [1.0]

    # Order:
    # "suservo_aom_singlepass_689_red_mot_sigmaplus",
    # "suservo_aom_singlepass_689_red_mot_sigmaminus",
    # "suservo_aom_singlepass_689_red_mot_diagonal",
    # "suservo_aom_singlepass_689_up",
    default_suservo_setpoint_multiples_start = [0.1, 0.1, 0.1, 0.0]
    default_suservo_setpoint_multiples_end = [0.02, 0.02, 0.02, 0.0]
