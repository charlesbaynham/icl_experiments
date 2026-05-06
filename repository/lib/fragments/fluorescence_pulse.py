import logging
from typing import List
from typing import Optional

from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

import repository.lib.constants as constants
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)

logger = logging.getLogger(__name__)


class FluorescencePulseBase(Fragment):
    """
    Pulse a beam onto the atoms

    This must be subclassed to specify which beam you want
    """

    suservo_beam_infos: Optional[List[SUServoedBeam]] = None
    "List of SUServoedBeam objects to use as fluorescence pulses. Must be provided by subclasses"
    urukul_beam_infos: Optional[List[UrukuledBeam]] = None
    "List of UrukuledBeam objects to use as fluorescence pulses. Must be provided by subclasses"

    def build_fragment(self) -> None:
        if self.suservo_beam_infos is None and self.urukul_beam_infos is None:
            raise TypeError(
                "Do not use this class directly - you must subclass it and provide a list of beam_infos"
            )

        self.suservo_beam_infos = self.suservo_beam_infos or []
        self.urukul_beam_infos = self.urukul_beam_infos or []

        _ImagingBeamsToggler = make_toggle_list_of_beams(
            suservo_beam_infos=self.suservo_beam_infos,
            urukul_beam_infos=self.urukul_beam_infos,
        )
        _ImagingBeamsSetter = make_set_beams_to_default(
            suservo_beam_infos=self.suservo_beam_infos,
            urukul_beam_infos=self.urukul_beam_infos,
            name="ImagingBeamsSettings",
        )

        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("all_beam_default_setter", _ImagingBeamsSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment("all_beam_toggler", _ImagingBeamsToggler)
        self.all_beam_toggler: ToggleListOfBeams

        # Also set up the fluorescence delivery AOM, regardless of which beams we're flashing
        self.setattr_fragment(
            "delivery_beam_setter",
            make_set_beams_to_default(
                [constants.SUSERVOED_BEAMS["blue_imaging_delivery"]],
                name="DeliveryBeamSettings",
            ),
        )
        self.delivery_beam_setter: SetBeamsToDefaults

        # Create a toggler for the delivery AOM, to allow it to be switched earlier from the fluorescence beam
        self.setattr_fragment(
            "delivery_beam_toggler",
            make_toggle_list_of_beams(
                [constants.SUSERVOED_BEAMS["blue_imaging_delivery"]],
            ),
        )
        self.delivery_beam_toggler: ToggleListOfBeams

        self.setattr_param(
            "fluorescence_pulse_duration",
            FloatParam,
            "Duration of the imaging pulse",
            default=constants.DEFAULT_IMAGING_PULSE,
            unit="us",
            min=0,
        )
        self.fluorescence_pulse_duration: FloatParamHandle

        self.setattr_param(
            "delivery_settling_duration",
            FloatParam,
            "Duration of the settling time for the imaging delivery AOM",
            default=constants.DEFAULT_DELIVERY_SETTLING_DURATION,
            unit="us",
            min=0,
        )
        self.delivery_settling_duration: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter.turn_on_all(light_enabled=False)
        self.delivery_beam_setter.turn_on_all(light_enabled=False)

    @kernel
    def do_imaging_pulse(
        self, ignore_initial_shutters=False, ignore_final_shutters=False, duration=-1.0
    ):
        """
        Do an imaging pulse. Camera control is left to the user.

        Use `fluorescence_pulse_duration` as the duration if `duration` is < 0.

        Advances the timeline by the duration of the pulse.
        """
        if duration < 0:
            duration = self.fluorescence_pulse_duration.get()
        delivery_settling_duration_mu = self.core.seconds_to_mu(
            self.delivery_settling_duration.get()
        )
        delay_mu(-delivery_settling_duration_mu)
        self.delivery_beam_toggler.turn_on_beams(
            ignore_shutters=ignore_initial_shutters
        )
        delay_mu(delivery_settling_duration_mu)
        self.all_beam_toggler.turn_on_beams(ignore_shutters=ignore_initial_shutters)
        delay(duration)
        self.all_beam_toggler.turn_off_beams(ignore_shutters=ignore_final_shutters)
        delay_mu(
            int64(self.core.ref_multiplier)
        )  # minimum delay to avoid use of extra lane (1 coarse rtio cycle)
        self.delivery_beam_toggler.turn_off_beams(ignore_shutters=ignore_final_shutters)

    @kernel
    def do_clearout_pulse(
        self, ignore_initial_shutters=False, ignore_final_shutters=False, duration=-1.0
    ):
        """
        Do a clearout pulse. Similar to the imaging pulse, but without any settling time for the delivery aom -
        both the delivery and switch turn on at the same time.

        Use `fluorescence_pulse_duration` as the duration if `duration` is < 0.

        Advances the timeline by the duration of the pulse.
        """
        if duration < 0:
            duration = self.fluorescence_pulse_duration.get()

        self.delivery_beam_toggler.turn_on_beams(
            ignore_shutters=ignore_initial_shutters
        )

        self.all_beam_toggler.turn_on_beams(ignore_shutters=ignore_initial_shutters)
        delay(duration)
        self.all_beam_toggler.turn_off_beams(ignore_shutters=ignore_final_shutters)
        delay_mu(
            int64(self.core.ref_multiplier)
        )  # minimum delay to avoid use of extra lane (1 coarse rtio cycle)
        self.delivery_beam_toggler.turn_off_beams(ignore_shutters=ignore_final_shutters)


class ImagingFluorescencePulse(FluorescencePulseBase):
    """
    Control a fluorescence pulse with the dedicated imaging beam
    """

    urukul_beam_infos = [constants.URUKULED_BEAMS["blue_imaging_switch"]]


class MOTBeamFluorescencePulse(FluorescencePulseBase):
    """
    Control a fluorescence pulse with the blue MOT beams
    """

    suservo_beam_infos = [
        constants.SUSERVOED_BEAMS["blue_3dmot_radial"],
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

        # Detach both the FluorescencePulse fragments so that their setup /
        # teardown functions do not get called automatically. We only want to
        # call the one that we're using, so we'll call it manually
        self.detach_fragment(self.imaging_beam)
        self.detach_fragment(self.mot_beams)

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

        # Call manually for the imaging beam subfrags.
        # Unlike device_setup, always call host_setup otherwise we'll have invalid kernels
        self.mot_beams.host_setup()
        self.imaging_beam.host_setup()

        return super().host_setup()

    def host_cleanup(self):
        self.mot_beams.host_cleanup()
        self.imaging_beam.host_cleanup()

        return super().host_cleanup()

    @kernel
    def device_setup(self) -> None:
        # Call manually for the imaging beam subfrags, only using the one we want
        if self.image_with_mot_beams_invariant:
            self.mot_beams.device_setup()
        else:
            self.imaging_beam.device_setup()

        self.device_setup_subfragments()

    @kernel
    def device_cleanup(self) -> None:
        # Call manually for the imaging beam subfrags, only using the one we want
        if self.image_with_mot_beams_invariant:
            self.mot_beams.device_cleanup()
        else:
            self.imaging_beam.device_cleanup()

        self.device_cleanup_subfragments()

    @kernel
    def do_imaging_pulse(
        self, ignore_initial_shutters=False, ignore_final_shutters=False, duration=-1.0
    ):
        """
        Do an imaging pulse with the requested beams. Camera control is left to the user.

        Use `fluorescence_pulse_duration` as the duration if `duration` is < 0.

        Advances the timeline by the duration of the pulse.
        """
        if self.image_with_mot_beams_invariant:
            self.mot_beams.do_imaging_pulse(
                ignore_initial_shutters=ignore_initial_shutters,
                ignore_final_shutters=ignore_final_shutters,
                duration=duration,
            )
        else:
            self.imaging_beam.do_imaging_pulse(
                ignore_initial_shutters=ignore_initial_shutters,
                ignore_final_shutters=ignore_final_shutters,
                duration=duration,
            )
