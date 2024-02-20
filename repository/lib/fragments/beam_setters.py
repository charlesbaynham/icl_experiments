import logging
import warnings
from typing import List
from typing import Tuple
from typing import Type

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import HasEnvironment
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.lib.utils import get_local_devices
from pyaion.models import SUServoedBeam


logger = logging.getLogger(__name__)


def make_set_beams_to_default(
    beam_infos: List[SUServoedBeam],
) -> Type["SetBeamsToDefaults"]:
    """
    Return a SetBeamsToDefaults Fragment class with the given beams set

    This is a factory method while builds a new class with the given beams
    configured. This is required because ARTIQ needs all instances of a given
    class to have the exact same attributes, and ndscan assumes that all
    `setattr_fragment` calls in a Fragment's `build_fragment` will have the same
    order, number and type-signatures. That's not true for this Fragment: we'll
    be setting up variable numbers of LibSetSUServoStatic subfragments, so need
    a subclass for each instance.
    """

    class SetBeamsToDefaultsCustomised(SetBeamsToDefaults):
        default_beam_infos = beam_infos

    return SetBeamsToDefaultsCustomised


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of suservoed beams, possibly with shutters, to their default
    settings

    Don't use this fragment directly: instead, construct it using
    :meth:`make_toggle_list_of_beams`.

    This class will define ndscan parameters which allow the user to override
    these default settings.
    """

    default_beam_infos: List[SUServoedBeam] = None  # type: ignore

    def build_fragment(self, default_beam_infos=None):
        if not self.default_beam_infos and default_beam_infos:
            warnings.warn(
                (
                    "Building SetBeamsToDefault with parameters passed to build_fragment. "
                    "This is not recommended: use the factory function instead"
                ),
                DeprecationWarning,
            )

        self.default_beam_infos = default_beam_infos or self.default_beam_infos

        if self.default_beam_infos is None:
            raise TypeError(
                "You must either create a subclass of SetBeamsToDefaults or pass in a list of default_beam_infos - see the documentation"
            )

        self.setattr_device("core")
        self.core: Core

        self.suservo_setters_and_info: List[
            Tuple[LibSetSUServoStatic, FloatParamHandle, bool]
        ] = []
        """
        Tuple of (
            LibSetSUServoStatic - setter interface
            FloatParamHandle - handle to setpoint parameter
            bool - does this SUServo have a shutter?
        )
        """

        self.ttls = []

        for beam_info in self.default_beam_infos:
            setter = self.setattr_fragment(
                beam_info.name, LibSetSUServoStatic, beam_info.suservo_device
            )

            if beam_info.shutter_device:
                self.ttls.append(self.get_device(beam_info.shutter_device))

            setpoint_handle = self.setattr_param(
                f"setpoint_{beam_info.name}",
                FloatParam,
                f"SUServo setpoint for {beam_info.name}",
                min=0,
                unit="V",
                default=beam_info.setpoint,
            )

            self.suservo_setters_and_info.append(
                (setter, setpoint_handle, bool(beam_info.shutter_device))
            )

        self.max_shutter_delay = max(
            [beam_info.shutter_delay for beam_info in self.default_beam_infos]
        )

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        # Add a dummy element to self.ttls to trick the ARTIQ compiler in the
        # case of empty lists. We loop from 1 onwards
        self.ttls.insert(0, self.get_device(get_local_devices(self, TTLOut)[0]))

        # %% Kernel invariants and variables
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "max_shutter_delay"}

        # Init this array to zeros - we fill it in in device_setup
        self.suservo_setpoints = [0.0] * len(self.default_beam_infos)

    @kernel
    def get_suservo_setpoint_by_index(self, beam_index):
        """
        Get the nominal setpoint for a given beam (allowing the user to override it)
        """
        return self.suservo_setpoints[beam_index]

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Retrieve the values of all the generated parameters for SUServo
        # setpoints for this run of the scan
        for i in range(len(self.suservo_setters_and_info)):
            setpoint_handle = self.suservo_setters_and_info[i][1]
            self.suservo_setpoints[i] = setpoint_handle.get()

    @portable
    def get_max_shutter_delay(self):
        return self.max_shutter_delay

    @kernel
    def turn_on_all(self, light_enabled=True):
        """
        Turn on the pre-configured beams to their default values

        If `light_enabled == False` and a shutter is present, close the shutter
        and enable the AOM.

        If `light_enabled == False` and no shutter is present, disable the AOM.

        This method does not respect shutter delays - it just turns everything
        on immediately.

        This method advances the timeline by the time required to perform
        several suservo writes and ttl updates separated by 8mu each
        """
        if self.debug_mode:
            logger.info(
                "SetBeamsToDefault.turn_on_all(light_enabled=%s)", light_enabled
            )

        for i in range(len(self.default_beam_infos)):
            (setter, setpoint_handle, shutter_present) = self.suservo_setters_and_info[
                i
            ]
            beam_info = self.default_beam_infos[i]

            if self.debug_mode:
                logger.info("Setter (%s) - beam_info %s", setter, beam_info)

            rf_switch_state = light_enabled or (not light_enabled and shutter_present)

            setter.set_suservo(
                float(beam_info.frequency),
                1.0,
                float(beam_info.attenuation),
                rf_switch_state=rf_switch_state,
                setpoint_v=setpoint_handle.get(),
                enable_iir=beam_info.servo_enabled,
            )

        for i in range(1, len(self.ttls)):
            ttl = self.ttls[i]
            ttl.set_o(light_enabled)
            delay_mu(8)


class DummySUServoFrag(HasEnvironment):
    """
    A dummy class that copies the interface of LibSetSUServoStatic

    This is used by ToggleListOfBeams when an empty list is passed to work
    around the ARTIQ compiler's bad handling of empty lists / arrays.
    """

    def build(self):
        self.setattr_device("core")

    @kernel
    def set_channel_state(self, rf_switch_state=True, enable_iir=True):
        pass


def make_toggle_list_of_beams(
    beam_infos: List[SUServoedBeam],
) -> Type["ToggleListOfBeams"]:
    """
    Factory function for :class:`~ToggleListOfBeams`. See documentation for
    :meth:`~make_set_beams_to_default` for reasoning.
    """

    class ToggleListOfBeamsCustomised(ToggleListOfBeams):
        default_beam_infos = beam_infos

    return ToggleListOfBeamsCustomised


class ToggleListOfBeams(Fragment):
    """
    Provides methods to turn on / off a list of beams simultaneously, with or
    without shutters

    Don't use this fragment directly: instead, construct it using
    :meth:`make_toggle_list_of_beams`.

    For each beam_info passed, this Fragment will either use
    :class:`pyaion.fragments.beam_setters.ControlBeamsWithoutCoolingAOM` to open
    / close the shutters in sequence with the toggling to AOM, respecting beam
    delays such that the beams turn on when requested. Or, if no shutter is
    present, this Fragment will simply turn on the beam (with or without the
    SUServo engaged, as defined).
    """

    default_beam_infos: List[SUServoedBeam] = None  # type: ignore

    def build_fragment(self, default_beam_infos=None):
        if not self.default_beam_infos and default_beam_infos:
            warnings.warn(
                (
                    "Building ToggleListOfBeams with parameters passed to build_fragment. "
                    "This is not recommended: use the factory function instead"
                ),
                DeprecationWarning,
            )

        self.default_beam_infos = default_beam_infos or self.default_beam_infos

        if self.default_beam_infos is None:
            raise TypeError(
                "You must either create a subclass of SetBeamsToDefaults"
                " or pass in a list of default_beam_infos"
                " - see the documentation"
            )

        self.setattr_device("core")
        self.core: Core

        # Filter our suservoed beams into ones with shutters and ones without
        self.beaminfos_with_shutters: List[SUServoedBeam] = list(
            filter(lambda i: bool(i.shutter_device), self.default_beam_infos)
        )
        self.beaminfos_without_shutters: List[SUServoedBeam] = list(
            filter(lambda i: not bool(i.shutter_device), self.default_beam_infos)
        )

        # Delegate to ControlBeamsWithoutCoolingAOM for the shutter-enabled beams
        self.setattr_fragment(
            "shuttered_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=self.beaminfos_with_shutters,
        )
        self.shuttered_beams_setter: ControlBeamsWithoutCoolingAOM

        # Build a list of LibSetSUServoStatics for the other beams
        self.suservo_frags: List[LibSetSUServoStatic] = []
        for beam in self.beaminfos_without_shutters:
            f = self.setattr_fragment(
                "suservofrag_" + beam.name,
                LibSetSUServoStatic,
                channel=beam.suservo_device,
            )
            self.suservo_frags.append(f)

        # Add a dummy beam / SUServo frag to the list if it's empty - see ARTIQ #1626
        if not self.suservo_frags:
            self.suservo_frags = [DummySUServoFrag(self)]

            dummy_beaminfo = SUServoedBeam(
                name="dummy",
                frequency=0,
                attenuation=0.0,
                shutter_device="dummy_shutter",
                suservo_device="dummy_suservo",
                shutter_delay=0,
            )
            self.beaminfos_without_shutters.insert(0, dummy_beaminfo)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "shuttered_beams_setter",
            "suservo_frags",
            "beaminfos_with_shutters",
            "beaminfos_without_shutters",
        }

    @kernel
    def turn_on_beams(self, ignore_shutters=False):
        # Turn on the shuttered beams
        self.shuttered_beams_setter.turn_beams_on(ignore_shutters=ignore_shutters)

        # And the unshuttered beams
        for i in range(len(self.suservo_frags)):
            beam_info = self.beaminfos_without_shutters[i]
            suservo_frag = self.suservo_frags[i]

            suservo_frag.set_channel_state(
                rf_switch_state=True, enable_iir=beam_info.servo_enabled
            )

    @kernel
    def turn_off_beams(self, ignore_shutters=False):
        # Turn off the shuttered beams
        self.shuttered_beams_setter.turn_beams_off(ignore_shutters=ignore_shutters)

        # And the unshuttered beams
        for i in range(len(self.suservo_frags)):
            beam_info = self.beaminfos_without_shutters[i]
            suservo_frag = self.suservo_frags[i]

            suservo_frag.set_channel_state(rf_switch_state=False, enable_iir=False)
