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
from artiq.coredevice.urukul import CPLD as UrukulCPLD
from artiq.experiment import delay_mu
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.dummy_devices import *
from repository.lib.fragments.beams.urukul_init import make_urukul_init


logger = logging.getLogger(__name__)


def make_set_beams_to_default(
    suservo_beam_infos: List[SUServoedBeam] = [],
    urukul_beam_infos: List[UrukuledBeam] = [],
    name="",
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

    if not name:
        name = "SetBeamsToDefaults"
        warnings.warn(
            "No name provided for default beam setter. Consider providing one to improve ndscan fragment naming"
        )

    SetBeamsToDefaultsCustomised.__name__ = name
    SetBeamsToDefaultsCustomised.__qualname__ = name

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
        self.default_suservo_beam_infos = self.default_suservo_beam_infos or []
        self.default_urukul_beam_infos = self.default_urukul_beam_infos or []

        if (
            self.default_suservo_beam_infos is []
            and self.default_urukul_beam_infos is []
        ):
            raise TypeError(
                "You must construct this class using the factory function make_set_beams_to_default"
                " or by subclassing this class and defining default_suservo_beam_infos or default_urukul_beam_infos"
            )

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

        # Ensure the AD9910 and AD9912s are initiated
        self.setattr_fragment(
            "urukul_init",
            make_urukul_init([b.urukul_device for b in self.default_urukul_beam_infos]),
        )

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

        self._turn_on_suservos(light_enabled=light_enabled)
        self._turn_on_ad9910s(light_enabled=light_enabled)
        self._turn_on_ad9912s(light_enabled=light_enabled)

    def _turn_on_suservos(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_suservos")

        for i in range(len(self.suservo_setters_and_info)):
            (setter, setpoint_handle, shutter_present) = self.suservo_setters_and_info[
                i
            ]
            beam_info = self.default_suservo_beam_infos[i]
            setpoint = setpoint_handle.get()

            rf_switch_state = light_enabled or (not light_enabled and shutter_present)

            if self.debug_mode:
                logger.info(
                    "Enabling suservo (%s)\n- beam_info %s\n- setpoint %s\n- rf_switch_state %s",
                    setter,
                    beam_info,
                    setpoint,
                    rf_switch_state,
                )

            setter.set_suservo(
                float(beam_info.frequency),
                1.0,
                float(beam_info.attenuation),
                rf_switch_state=rf_switch_state,
                setpoint_v=setpoint,
                enable_iir=beam_info.servo_enabled,
            )

            logger.warning("DONE")  # FIXME

    def _turn_on_ad9910s(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_ad9910s")

        for (
            ad9910_device,
            frequency_handle,
            amplitude_handle,
            shutter_present,
        ) in self.ad9910_devices_and_handles:
            rf_switch_state = light_enabled or (not light_enabled and shutter_present)
            freq = frequency_handle.get()
            amp = amplitude_handle.get()

            ad9910_device.set(frequency=freq, amplitude=amp)
            ad9910_device.sw.set_o(rf_switch_state)

            if self.debug_mode:
                logger.info(
                    "Enabling AD9910 %s, freq=%s, amp=%s", ad9910_device, freq, amp
                )

    def _turn_on_ad9912s(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_ad9912s")

        for (
            ad9912_device,
            frequency_handle,
            shutter_present,
        ) in self.ad9912_devices_and_handles:
            rf_switch_state = light_enabled or (not light_enabled and shutter_present)
            freq = frequency_handle.get()

            ad9912_device.set(frequency=freq)
            ad9912_device.sw.set_o(rf_switch_state)

            if self.debug_mode:
                logger.info("Enabling AD9910 %s, freq=%s", ad9912_device, freq)

        for ttl in self.ttls:
            ttl.set_o(light_enabled)
            delay_mu(8)
