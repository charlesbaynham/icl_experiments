import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import make_set_beams_to_default
from repository.lib.fragments.beam_setters import make_toggle_list_of_beams
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.beam_setters import ToggleListOfBeams


logger = logging.getLogger(__name__)


class FluorescencePulse(Fragment):
    """
    Pulse the imaging beam onto the atoms
    """

    beam_infos = [constants.AOM_BEAMS["blue_imaging_switch"]]
    "By default, use the imaging beam switch AOM"

    def build_fragment(self) -> None:
        _ImagingBeamsToggler = make_toggle_list_of_beams(self.beam_infos)
        _ImagingBeamsSetter = make_set_beams_to_default(self.beam_infos)

        self.setattr_device("core")
        self.core: Core

        # Accept a list of SUServoedBeams describing which beams to flash for the flourescence
        self.setattr_fragment("all_beam_default_setter", _ImagingBeamsSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment("all_beam_toggler", _ImagingBeamsToggler)
        self.all_beam_toggler: ToggleListOfBeams

        # Also set up the flourescence delivery AOM, regardless of which beams we're flashing
        self.setattr_fragment(
            "delivery_beam_setter",
            make_set_beams_to_default([constants.AOM_BEAMS["blue_imaging_delivery"]]),
        )
        self.delivery_beam_setter: SetBeamsToDefaults

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

        # # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter.turn_on_all(light_enabled=False)
        self.delivery_beam_setter.turn_on_all(light_enabled=True)

    @kernel
    def do_imaging_pulse(self):
        """
        Do an imaging pulse. Camera control is left to the user.

        Advances the timeline by `flourescence_pulse_duration`.
        """
        self.all_beam_toggler.turn_on_beams()
        delay(self.flourescence_pulse_duration.get())
        self.all_beam_toggler.turn_off_beams()


class MOTBeamFluorescencePulse(FluorescencePulse):
    beam_infos = [
        constants.AOM_BEAMS["blue_3dmot_axialminus"],
        constants.AOM_BEAMS["blue_3dmot_axialplus"],
        constants.AOM_BEAMS["blue_3dmot_radial"],
    ]
