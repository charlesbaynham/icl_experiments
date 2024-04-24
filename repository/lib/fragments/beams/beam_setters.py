import logging
import warnings
from typing import Dict
from typing import List
from typing import Tuple
from typing import Type
from typing import Union

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.coredevice.core import parallel
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.urukul import CPLD as UrukulCPLD
from artiq.experiment import delay_mu
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.dummy_devices import *


logger = logging.getLogger(__name__)


def make_set_beams_to_default(
    suservo_beam_infos: List[SUServoedBeam] = [],
    urukul_beam_infos: List[UrukuledBeam] = [],
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
        default_suservo_beam_infos = suservo_beam_infos
        default_urukul_beam_infos = urukul_beam_infos

    return SetBeamsToDefaultsCustomised


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of beams, possibly with shutters, to their default
    settings

    These can be suservoed or urukuled beams.

    Don't use this fragment directly: instead, construct it using
    :meth:`make_toggle_list_of_beams`.

    This class will define ndscan parameters which allow the user to override
    these default settings.
    """

    default_suservo_beam_infos: List[SUServoedBeam] = None  # type: ignore
    default_urukul_beam_infos: List[UrukuledBeam] = None  # type: ignore

    def build_fragment(self):
        if (
            self.default_suservo_beam_infos is None
            and self.default_urukul_beam_infos is None
        ):
            raise TypeError(
                "You must construct this class using the factory function make_set_beams_to_default"
                " or by subclassing this class and defining default_suservo_beam_infos or default_urukul_beam_infos"
            )

        self.default_suservo_beam_infos = self.default_suservo_beam_infos or []
        self.default_urukul_beam_infos = self.default_urukul_beam_infos or []

        self.setattr_device("core")
        self.core: Core

        self.dummy_ttl = DummyTTL()
        self.dummy_ad9910 = DummyAD9910()
        self.dummy_ad9912 = DummyAD9912()
        self.dummy_urukul = DummyUrukul()
        self.dummy_suservo_frag = DummySUServoFrag()
        self.dummy_float_handle = DummyFloatParameterHandle()

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

        # Loop over all the suservo beams, defining:
        #   * LibSetSUServoStatic fragments to control them
        #   * Parameters for their setpoints
        #   * Devices for their shutters, if defined
        for beam_info in self.default_suservo_beam_infos:
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

        # %% Urukul settings

        self.ad9910s: List[AD9910] = []
        self.ad9912s: List[AD9910] = []
        self.urukuls: List[UrukulCPLD] = []

        self.ad9910_devices_and_handles: List[
            Tuple[AD9910, FloatParamHandle, FloatParamHandle, bool]
        ] = []
        """
        Tuple of (
            AD9910 - ARTIQ device
            FloatParamHandle - handle to frequency parameter
            FloatParamHandle - handle to amplitude parameter
            bool - does this beam have a shutter?
        )
        """

        self.ad9912_devices_and_handles: List[
            Tuple[AD9912, FloatParamHandle, FloatParamHandle, bool]
        ] = []
        """
        Tuple of (
            AD9912 - ARTIQ device
            FloatParamHandle - handle to frequency parameter
            bool - does this beam have a shutter?
        )
        """

        for beam_info in self.default_urukul_beam_infos:
            device: Union[AD9910, AD9912] = self.get_device(beam_info.urukul_device)

            self.urukuls.append(device.cpld)

            if beam_info.shutter_device:
                self.ttls.append(self.get_device(beam_info.shutter_device))

            frequency_handle = self.setattr_param(
                f"frequency_{beam_info.name}",
                FloatParam,
                f"Frequency for {beam_info.name}",
                min=0,
                max=500e6,
                default=beam_info.frequency,
            )

            if isinstance(device, AD9910):
                amplitude_handle = self.setattr_param(
                    f"amplitude_{beam_info.name}",
                    FloatParam,
                    f"Amplitude for {beam_info.name}",
                    min=0,
                    max=1,
                    default=beam_info.amplitude,
                )

                self.ad9910_devices_and_handles.append(
                    (
                        device,
                        frequency_handle,
                        amplitude_handle,
                        bool(beam_info.shutter_device),
                    )
                )
            elif isinstance(device, AD9912):
                self.ad9912_devices_and_handles.append(
                    (
                        device,
                        frequency_handle,
                        bool(beam_info.shutter_device),
                    )
                )
            else:
                raise TypeError("Unrecognised device type")

        # Filter out duplicates
        self.urukuls = list(set(self.urukuls))

        self.max_shutter_delay = max(
            [
                beam_info.shutter_delay
                for beam_info in (
                    self.default_suservo_beam_infos + self.default_urukul_beam_infos
                )
            ]
        )

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        # %% Dummy elements

        # This code is annoying. We must work around ARTIQ's inability to infer
        # the type of empty lists by making sure that the lists are not empty.
        # That means adding object to them which have the same call structure as
        # the real ones, but actually do nothing. The compiler will optimize
        # these away so they won't have an impact on performance.

        if not self.ttls:
            self.ttls = [self.dummy_ttl]

        if not self.ad9910_devices_and_handles:
            self.ad9910_devices_and_handles = [
                (
                    self.dummy_ad9910,
                    self.dummy_float_handle,
                    self.dummy_float_handle,
                    False,
                )
            ]

        if not self.ad9912_devices_and_handles:
            self.ad9912_devices_and_handles = [
                (
                    self.dummy_ad9912,
                    self.dummy_float_handle,
                    False,
                )
            ]

        if not self.suservo_setters_and_info:
            self.suservo_setters_and_info = [
                (self.dummy_suservo_frag, self.dummy_float_handle, False)
            ]
            self.default_suservo_beam_infos = [
                SUServoedBeam(
                    name="", frequency=0.0, attenuation=0.0, suservo_device=""
                )
            ]

        if not self.ad9910s:
            self.ad9910s = [self.dummy_ad9910]

        if not self.ad9912s:
            self.ad9912s = [self.dummy_ad9912]

        if not self.urukuls:
            self.urukuls = [self.dummy_urukul]

        # %% Kernel invariants and variables
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "max_shutter_delay"}

        # Init this array to zeros - we fill it in in device_setup
        self.suservo_setpoints = [0.0] * len(self.default_suservo_beam_infos)
        self.first_run = True

    @kernel
    def get_suservo_setpoint_by_index(self, beam_index):
        """
        Get the nominal setpoint for a given beam (allowing the user to override it)
        """
        return self.suservo_setpoints[beam_index]

    @host_only
    def get_setpoints_and_beaminfo_dict(
        self,
    ) -> Dict[str, Tuple[SUServoedBeam, FloatParamHandle]]:
        """
        Get a dict of beam name -> (:class:`~SUServoedBeam` beam info,
        :class:`~FloatParamHandle` handle to suservo setpoint)
        """
        out = {}
        for beam_info, (_, handle, _) in zip(
            self.default_suservo_beam_infos, self.suservo_setters_and_info
        ):
            out[beam_info.name] = (beam_info, handle)
        return out

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Initiate AD9910s if not done yet
        if self.first_run:
            self.first_run = False

            self.core.break_realtime()

            with parallel:
                for urukul in self.urukuls:
                    # TODO: Initiating Urukuls like this is inefficient since many
                    # will be in multiple beam setters and so will be initiated
                    # multiple times. See the code in LibSetSUServoStatic for ways
                    # to avoid this
                    urukul.init()

            self.core.break_realtime()

            with parallel:
                for ad9910 in self.ad9910s:
                    ad9910.init()

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

        for i in range(len(self.suservo_setters_and_info)):
            (setter, setpoint_handle, shutter_present) = self.suservo_setters_and_info[
                i
            ]
            beam_info = self.default_suservo_beam_infos[i]

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

        for i in range(len(self.ad9910_devices_and_handles)):
            (
                ad9910_device,
                frequency_handle,
                amplitude_handle,
                shutter_present,
            ) = self.ad9910_devices_and_handles[i]

            rf_switch_state = light_enabled or (not light_enabled and shutter_present)

            ad9910_device.set(
                frequency=frequency_handle.get(), amplitude=amplitude_handle.get()
            )
            ad9910_device.sw.set_o(rf_switch_state)

        for ttl in self.ttls:
            ttl.set_o(light_enabled)
            delay_mu(8)


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
            self.suservo_frags = [_DummySUServoFrag(self)]

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
