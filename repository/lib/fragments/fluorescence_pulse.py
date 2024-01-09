import logging
from typing import List
from typing import Optional

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.models import SUServoedBeam

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import make_set_beams_to_default
from repository.lib.fragments.beam_setters import make_toggle_list_of_beams
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.beam_setters import ToggleListOfBeams


logger = logging.getLogger(__name__)


class FluorescencePulseBase(Fragment):
    """
    Pulse a beam onto the atoms

    This must be subclassed to specify which beam you want
    """

    beam_infos: Optional[List[SUServoedBeam]] = None
    "List of SUServoedBeam objects to use as fluorescence pulses. Must be provided by subclasses"

    def build_fragment(self) -> None:
        if self.beam_infos is None:
            raise TypeError(
                "Do not use this class directly - you must subclass it and provide a list of beam_infos"
            )

        _ImagingBeamsToggler = make_toggle_list_of_beams(self.beam_infos)
        _ImagingBeamsSetter = make_set_beams_to_default(self.beam_infos)

        self.setattr_device("core")
        self.core: Core

        # Accept a list of SUServoedBeams describing which beams to flash for the fluorescence
        self.setattr_fragment("all_beam_default_setter", _ImagingBeamsSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment("all_beam_toggler", _ImagingBeamsToggler)
        self.all_beam_toggler: ToggleListOfBeams

        # Also set up the fluorescence delivery AOM, regardless of which beams we're flashing
        self.setattr_fragment(
            "delivery_beam_setter",
            make_set_beams_to_default([constants.AOM_BEAMS["blue_imaging_delivery"]]),
        )
        self.delivery_beam_setter: SetBeamsToDefaults

        self.setattr_param(
            "fluorescence_pulse_duration",
            FloatParam,
            "Duration of the imaging pulse",
            default=constants.DEFAULT_IMAGING_PULSE,
            unit="us",
            min=0,
        )
        self.fluorescence_pulse_duration: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter.turn_on_all(light_enabled=False)
        self.delivery_beam_setter.turn_on_all(light_enabled=True)

    @kernel
    def do_imaging_pulse(
        self,
        ignore_initial_shutters=False,
        ignore_final_shutters=False,
    ):
        """
        Do an imaging pulse. Camera control is left to the user.

        Advances the timeline by `fluorescence_pulse_duration`.
        """
        self.all_beam_toggler.turn_on_beams(ignore_shutters=ignore_initial_shutters)
        delay(self.fluorescence_pulse_duration.get())
        self.all_beam_toggler.turn_off_beams(ignore_shutters=ignore_final_shutters)


class ImagingFluorescencePulse(FluorescencePulseBase):
    """
    Control a fluorescence pulse with the dedicated imaging beam
    """

    beam_infos = [constants.AOM_BEAMS["blue_imaging_switch"]]


class MOTBeamFluorescencePulse(FluorescencePulseBase):
    """
    Control a fluorescence pulse with the blue MOT beams
    """

    beam_infos = [
        constants.AOM_BEAMS["blue_3dmot_axialminus"],
        constants.AOM_BEAMS["blue_3dmot_axialplus"],
        # constants.AOM_BEAMS["blue_3dmot_radial"],
    ]


class ToggleableFluorescencePulse(Fragment):
    """
    Use either the blue MOT beams or the dedicated imaging beam for
    fluorescence, controllable by a parameter
    """

    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_fragment("imaging_beam", ImagingFluorescencePulse)
        self.setattr_fragment("mot_beams", MOTBeamFluorescencePulse)
        self.imaging_beam: FluorescencePulseBase
        self.mot_beams: FluorescencePulseBase

        # Rebind the pulse durations so they are both controlled from this fragment
        self.setattr_param_like("fluorescence_pulse_duration", self.imaging_beam)
        self.imaging_beam.bind_param(
            "fluorescence_pulse_duration", self.fluorescence_pulse_duration
        )
        self.mot_beams.bind_param(
            "fluorescence_pulse_duration", self.fluorescence_pulse_duration
        )
        self.fluorescence_pulse_duration: FloatParamHandle

        self.setattr_param(
            "image_with_mot_beams",
            BoolParam,
            "Image with MOT beams instead of fluorescence beam",
            default=False,
        )
        self.image_with_mot_beams: BoolParamHandle

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "image_with_mot_beams_invariant",
        }

    def host_setup(self):
        # Optimization - bools cannot be scanned, so bake it in as a kernel invariant
        self.image_with_mot_beams_invariant = self.image_with_mot_beams.get()
        return super().host_setup()

    @kernel
    def do_imaging_pulse(
        self, ignore_initial_shutters=False, ignore_final_shutters=False
    ):
        """
        Do an imaging pulse with the requested beams. Camera control is left to the user.

        Advances the timeline by `fluorescence_pulse_duration`.
        """
        if self.image_with_mot_beams.get():
            self.mot_beams.do_imaging_pulse(
                ignore_initial_shutters=ignore_initial_shutters,
                ignore_final_shutters=ignore_final_shutters,
            )
        else:
            self.imaging_beam.do_imaging_pulse(
                ignore_initial_shutters=ignore_initial_shutters,
                ignore_final_shutters=ignore_final_shutters,
            )
