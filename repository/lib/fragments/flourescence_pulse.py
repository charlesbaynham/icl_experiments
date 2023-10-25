import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.suservo import LibSetSUServoStatic

logger = logging.getLogger(__name__)


class ImagingBeamSetter(SetBeamsToDefaults):
    default_beam_infos = [
        constants.AOM_BEAMS[beam]
        for beam in [
            "blue_imaging_delivery",
            "blue_imaging_switch",
        ]
    ]


class FlourescencePulse(Fragment):
    """
    Pulse the imaging beam onto the atoms
    """

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("all_beam_default_setter", ImagingBeamSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.delivery_suservo: LibSetSUServoStatic = self.setattr_fragment(
            "delivery_suservo",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_imaging_delivery",
        )

        self.switch_suservo: LibSetSUServoStatic = self.setattr_fragment(
            "switch_suservo",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_imaging_switch",
        )

        self.setattr_param(
            "flourescence_pulse_duration",
            FloatParam,
            "Duration of the imaging pulse",
            default=constants.DEFAULT_IMAGING_PULSE,
            unit="us",
            min=0,
        )
        self.flourescence_pulse_duration: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Configure and enable the SUServos for both AOMs
        self.all_beam_default_setter.turn_on_all(light_enabled=False)
        # Turn on the "delivery" SUServo immediately - this light does not reach the atoms
        self.delivery_suservo.set_channel_state(True, True)

    @kernel
    def do_imaging_pulse(self):
        """
        Do an imaging pulse. Camera control is left to the user.

        Advances the timeline by `flourescence_pulse_duration`.
        """
        self.switch_suservo.set_channel_state(True, False)
        delay(self.flourescence_pulse_duration.get())
        self.switch_suservo.set_channel_state(False, False)
