import logging

from artiq.experiment import host_only
from artiq.experiment import kernel
from pyaion.fragments.ramping_phase import GeneralRampingPhase

from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.pyaion_overrides.default_beam_setter_override import (
    SetBeamsToDefaults,
)

logger = logging.getLogger(__name__)


class GeneralRampingPhaseWithBinding(GeneralRampingPhase):
    """
    Template fragment for a phase of the experiment using a ramp with bound SUServo setpoints.

    This adds to the functionality
    of :class:`~GeneralRampingPhase` with a method binding the ramp SUServo setpoints
    to the default setpoints in an instance of :class:`~SetBeamsToDefaults`, or a list of instances of :class:`~SetBeamsToDefaults`. This is useful
    for having a common reference "default" setpoint used in both the ramp and other
    stages in the sequence, while exposing that default as a parameter in ndscan.

    See the docs for :class:`~GeneralRampingPhase` for more information.
    """

    def build_fragment(self, enforce_binding_to_defaults=True):
        self.enforce_binding_to_defaults = enforce_binding_to_defaults
        self.__binding_completed = False
        return super().build_fragment()

    def host_setup(self):
        if self.enforce_binding_to_defaults and not self.__binding_completed:
            raise TypeError(
                "bind_suservo_setpoint_params_to_default_beam_setter has not been called\n"
                "This must be called from the Fragment which initiates this phase to rebind the red beam setpoints"
            )
        return super().host_setup()

    @host_only
    def bind_suservo_setpoint_params_to_default_beam_setter(
        self, beam_setter: SetBeamsToDefaults | list[SetBeamsToDefaults]
    ):
        """
        Use the GeneralRampingPhase's :meth:`~.bind_suservo_setpoint_params`
        method to bind all this GeneralRampingPhase's suservo setpoint
        parameters to those defined by a `SetBeamsToDefaults`, or a list of `SetBeamsToDefaults`.

        This binding method can be used to create a single place in the ndscan
        parameter tree where a global multiple for all the setpoints for a set of related beams are defined,
        e.g. for the red 689 nm beams, all setpoints are tied to the nominal setpoint in the SetBeamsToDefaults, owned by the red_beam_controller.

        Some envisaged use cases of nominal setpoint binding:

        1. Bind nominal setpoints to a `SetBeamsToDefaults` using this
           `bind_suservo_setpoint_params_to_default_beam_setter` method. This
           should be used to bind a ramp to a common reference in the case where
           beams have been set up using a previous
           SetBeamsToDefaults.turn_on_all().

        2. Bind nominal setpoints to the previous adjacent ramping phase using
           :meth:`~.daisy_chain_with_previous_phase`. This should be used when
           one ramp follows another and they should share the same nominal
           setpoints (and, optionally, end/start points).

        3. Don't bind nominal setpoints. The ramping phase nominal setpoint will
           then be free to tune independently of other phases (often not
           advisable if coordination between phases is useful).
        """
        # For the SUServo setpoints, bind these to the FloatParameters defined
        # by the DefaultBeamSetter so that this is the only place which defines
        # SUServo setpoints
        if isinstance(beam_setter, SetBeamsToDefaults):
            info_and_settings = list(
                beam_setter.get_setpoints_beaminfo_setters().values()
            )
            handles = []
            for suservo_device_name in self.suservos:
                for info, settings in info_and_settings:
                    if info.suservo_device == suservo_device_name:
                        handles.append(settings.setpoint_handle)
                        break
                else:
                    raise ValueError(
                        f"SUServo {suservo_device_name} not found in all_beam_default_setter"
                    )
            self.bind_suservo_setpoint_params(handles)
            self.__binding_completed = True
        else:
            handles = []
            for suservo_device_name in self.suservos:
                _found = False
                for beam_setter_instance in beam_setter:
                    if _found:
                        break
                    else:
                        info_and_settings = list(
                            beam_setter_instance.get_setpoints_beaminfo_setters().values()
                        )
                        for info, settings in info_and_settings:
                            if info.suservo_device == suservo_device_name:
                                handles.append(settings.setpoint_handle)
                                _found = True
                                break
                if not _found:
                    if self.enforce_binding_to_defaults:
                        raise ValueError(
                            f"SUServo {suservo_device_name} not found in all_beam_default_setters"
                        )
            if len(handles) != len(set(handles)):
                raise ValueError(
                    "Duplicate default SUServo setpoints in different beam_setters encountered"
                )
            self.bind_suservo_setpoint_params(handles)
            self.__binding_completed = True


class GeneralRampingPhaseWithBindingAndMOTField(GeneralRampingPhaseWithBinding):
    """
    Template fragment for a phase of the experiment using a ramp with bound SUServo setpoints and a ramping MOT field gradient.

    See the docs for :class:`~GeneralRampingPhaseWithBinding` for more information.
    """

    # The general ramp here ramps the chamber 2 MOT coils in amps

    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(self, **kwargs):
        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        return super().build_fragment(**kwargs)

    @kernel
    def general_setter(self, vals: list[float]):
        self.chamber_2_field_setter.set_mot_gradient(vals[0])


class GeneralRampingPhaseWithBindingAndBiasField(GeneralRampingPhaseWithBinding):
    """
    Template fragment for a phase of the experiment using a ramp with bound SUServo setpoints and a ramping bias magnetic field in x,y,z.

    See the docs for :class:`~GeneralRampingPhaseWithBinding` for more information.
    """

    general_setter_names = ["bias_field_x", "bias_field_y", "bias_field_z"]
    general_setter_param_options = [{"min": -10, "max": 10, "unit": "A"}] * 3

    def build_fragment(self, **kwargs):
        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        return super().build_fragment(**kwargs)

    @kernel
    def general_setter(self, vals: list[float]):
        self.chamber_2_field_setter.set_bias_fields(vals[0], vals[1], vals[2])


class GeneralRampingPhaseWithBindingAndMOTAndBiasField(GeneralRampingPhaseWithBinding):
    """
    Template fragment for a phase of the experiment using a ramp with bound SUServo setpoints,
    a ramping MOT field gradient, and a ramping bias magnetic field in x, y, z.

    See the docs for :class:`~GeneralRampingPhaseWithBinding` for more information.
    """

    general_setter_names = [
        "chamber_2_mot_current",
        "bias_field_x",
        "bias_field_y",
        "bias_field_z",
    ]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}] + [
        {"min": -10, "max": 10, "unit": "A"}
    ] * 3

    def build_fragment(self, **kwargs):
        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        return super().build_fragment(**kwargs)

    @kernel
    def general_setter(self, vals: list[float]):
        self.chamber_2_field_setter.set_all_fields(vals[0], vals[1], vals[2], vals[3])
