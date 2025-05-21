import logging
import warnings
from dataclasses import dataclass
from typing import *

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.urukul import CPLD as UrukulCPLD
from artiq.experiment import delay_mu
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.master.worker_db import DummyDevice
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.urukul_init import make_urukul_init
from pyaion.models import UrukuledBeam
from pyaion.utilities.dummy_devices import DummyCPLD as DummyUrukul
from pyaion.utilities.dummy_devices import *

from repository.lib.fragments.pyaion_overrides.models_override import SUServoedBeam

logger = logging.getLogger(__name__)


def make_set_beams_to_default(
    suservo_beam_infos: List[SUServoedBeam] = [],
    urukul_beam_infos: List[UrukuledBeam] = [],
    name="",
    use_automatic_setup=False,
    use_automatic_turnon=False,
) -> Type["SetBeamsToDefaults"]:
    """
    Return a SetBeamsToDefaults Fragment class with the given beams set

    This is a factory method while builds a new class with the given beams
    configured. This is required because ARTIQ needs all instances of a given
    class to have the exact same attributes, and ndscan assumes that all
    `setattr_fragment` calls in a Fragment's `build_fragment` will have the same
    order, number and type-signatures. That's not true for this `Fragment`:
    we'll be setting up variable numbers of `LibSetSUServoStatic` subfragments,
    so need a subclass for each instance.

    You can provide a `name` if you wish, which will result in nicer annotations
    for your ndscan parameters in the GUI.

    If `use_automatic_setup==True`, setup the AOM defaults in `device_setup`
    automatically. The beams will still be left off, but the frequency, gains,
    setpoints etc. will be configured.

    If `use_automatic_turnon==True`, turn the beams on automatically in
    `device_setup`. This requires `use_automatic_setup==True`.

    See the docs for :class:`~SetBeamsToDefaults` for more information.

    TODO: Idea: I could speed up compilation times by sharing the same class
    definitions where possible, though this might be hard to detect.
    """

    class SetBeamsToDefaultsCustomised(SetBeamsToDefaults):
        default_suservo_beam_infos = suservo_beam_infos
        default_urukul_beam_infos = urukul_beam_infos
        automatic_setup = use_automatic_setup
        automatic_turnon = use_automatic_turnon

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
    Turn on a list of beams, possibly with shutters, to their default settings

    These can be suservoed or urukuled beams, of the AD9910 or AD9912 variety.

    This Fragment will create ndscan parameters for all the beam settings,
    allowing you to override them or scan them if you wish.

    This Fragment provides the :meth:`~turn_on_all` method which will initiate
    all the AD9910 / AD9912 / SUServos to their appropriate settings. By default
    it will leave the light off, requiring you to turn it on (you could consider
    the :class:`~ToggleListOfBeams` Fragment for this purpose). If you just want
    the light to be on immediately, set `light_enabled=True`.

    Usage
    -----

    Don't use this fragment directly: instead, construct it using
    :meth:`make_set_beams_to_default`. For example, in your `build_fragment`::

        self.setattr_fragment(
            "red_beam_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["red_mot_diagonal"],
                    constants.SUSERVOED_BEAMS["red_mot_sigmaplus"],
                    constants.SUSERVOED_BEAMS["red_mot_sigmaminus"],
                    constants.SUSERVOED_BEAMS["red_up"],
                ],
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["red_doublepass_injection"],
                ],
                name="red_beam_setter",
            ),
        )
        self.red_beam_setter: SetBeamsToDefaults
    """

    default_suservo_beam_infos: List[SUServoedBeam] = None  # type: ignore
    default_urukul_beam_infos: List[UrukuledBeam] = None  # type: ignore
    automatic_setup = False
    automatic_turnon = False

    def build_fragment(self):
        self.default_suservo_beam_infos = self.default_suservo_beam_infos or []
        self.default_urukul_beam_infos = self.default_urukul_beam_infos or []

        # automatic_setup and automatic_turnon are class variables, but add them to kernel invariants anyway
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("automatic_setup")
        self.kernel_invariants.add("automatic_turnon")

        if self.automatic_turnon and not self.automatic_setup:
            raise ValueError(
                "automatic_turnon requires automatic_setup to be True as well"
            )

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

        # SUServo settings

        self.shutter_ttls: List[TTLOut] = []

        @dataclass
        class SUServoSettings:
            setter: LibSetSUServoStatic
            setpoint_handle: FloatParamHandle
            shutter_present: bool
            initial_amplitude_handle: FloatParamHandle
            frequency_handle: FloatParamHandle

        self.suservo_setters_and_info: List[SUServoSettings] = []

        # Loop over all the suservo beams, defining:
        #   * LibSetSUServoStatic fragments to control them
        #   * Parameters for their setpoints
        #   * Devices for their shutters, if defined
        for beam_info in self.default_suservo_beam_infos:
            setter = self.setattr_fragment(
                beam_info.name, LibSetSUServoStatic, beam_info.suservo_device
            )

            if beam_info.shutter_device:
                self.shutter_ttls.append(self.get_device(beam_info.shutter_device))

            setpoint_handle = self.setattr_param(
                f"setpoint_{beam_info.name}",
                FloatParam,
                f"SUServo setpoint for {beam_info.name}",
                min=0,
                unit="V",
                default=beam_info.setpoint,
            )

            amplitude_handle = self.setattr_param(
                f"amplitude_{beam_info.name}",
                FloatParam,
                f"SUServo initial amplitude for {beam_info.name}",
                min=0,
                max=1,
                default=beam_info.initial_amplitude,
            )

            frequency_handle = self.setattr_param(
                f"frequency_{beam_info.name}",
                FloatParam,
                f"SUServo frequency for {beam_info.name}",
                min=0,
                unit="MHz",
                default=beam_info.frequency,
            )

            self.suservo_setters_and_info.append(
                SUServoSettings(
                    setter=setter,
                    setpoint_handle=setpoint_handle,
                    shutter_present=bool(beam_info.shutter_device),
                    initial_amplitude_handle=amplitude_handle,
                    frequency_handle=frequency_handle,
                )
            )

        # %% Urukul settings

        self.ad9910s: List[AD9910] = []
        self.ad9912s: List[AD9910] = []
        self.urukuls: List[UrukulCPLD] = []  # Populated in host_seutp
        self.switch_ttls_with_shutter: List[TTLOut] = []
        self.switch_ttls_without_shutter: List[TTLOut] = []

        @dataclass
        class AD9910Info:
            device: AD9910
            frequency_handle: FloatParamHandle
            amplitude_handle: FloatParamHandle
            attenuation: float
            shutter_present: bool
            has_ttl_switch: bool

        @dataclass
        class AD9912Info:
            device: AD9912
            frequency_handle: FloatParamHandle
            attenuation: float
            shutter_present: bool
            has_ttl_switch: bool

        self.ad9910_devices_and_handles: List[AD9910Info] = []
        self.ad9912_devices_and_handles: List[AD9912Info] = []

        for beam_info in self.default_urukul_beam_infos:
            device: Union[AD9910, AD9912] = self.get_device(beam_info.urukul_device)

            frequency_handle = self.setattr_param(
                f"frequency_{beam_info.name}",
                FloatParam,
                f"Frequency for {beam_info.name}",
                min=0,
                max=500e6,
                unit="MHz",
                default=beam_info.frequency,
            )

            if beam_info.shutter_device:
                self.shutter_ttls.append(self.get_device(beam_info.shutter_device))

            if isinstance(device, AD9910):
                amplitude_handle = self.setattr_param(
                    f"amplitude_{beam_info.name}",
                    FloatParam,
                    f"Amplitude for {beam_info.name}",
                    min=0,
                    max=1,
                    default=beam_info.amplitude,
                )

                info = AD9910Info(
                    device,
                    frequency_handle,
                    amplitude_handle,
                    beam_info.attenuation,
                    shutter_present=bool(beam_info.shutter_device),
                    has_ttl_switch=hasattr(device, "sw"),
                )
                self.ad9910_devices_and_handles.append(info)

            elif isinstance(device, AD9912):
                info = AD9912Info(
                    device,
                    frequency_handle,
                    beam_info.attenuation,
                    shutter_present=bool(beam_info.shutter_device),
                    has_ttl_switch=hasattr(device, "sw"),
                )
                if info.has_ttl_switch:
                    self.switch_ttls_with_shutter.append(device.sw)
                self.ad9912_devices_and_handles.append(info)

            elif isinstance(device, DummyDevice):
                info = None
            else:
                raise TypeError("Unrecognised device type")

            if info and info.has_ttl_switch:
                if info.shutter_present:
                    self.switch_ttls_with_shutter.append(device.sw)
                else:
                    self.switch_ttls_without_shutter.append(device.sw)

        # Ensure the AD9910 and AD9912s are initiated
        self.setattr_fragment(
            "urukul_init",
            make_urukul_init([b.urukul_device for b in self.default_urukul_beam_infos]),
        )

        self.max_shutter_delay = max(
            [
                beam_info.shutter_delay
                for beam_info in (
                    self.default_suservo_beam_infos + self.default_urukul_beam_infos
                )
            ]
            + [0]
        )

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        # %% Dummy elements

        # This code is annoying. We must work around ARTIQ's inability to infer
        # the type of empty lists by making sure that the lists are not empty.
        # That means adding object to them which have the same call structure as
        # the real ones, but actually do nothing. The compiler will optimize
        # these away so they won't have an impact on performance.

        if not self.shutter_ttls:
            self.shutter_ttls = [self.dummy_ttl]
        if not self.switch_ttls_with_shutter:
            self.switch_ttls_with_shutter = [self.dummy_ttl]
        if not self.switch_ttls_without_shutter:
            self.switch_ttls_without_shutter = [self.dummy_ttl]

        if not self.ad9910_devices_and_handles:
            self.ad9910_devices_and_handles = [
                AD9910Info(
                    self.dummy_ad9910,
                    self.dummy_float_handle,
                    self.dummy_float_handle,
                    0.0,
                    False,
                    False,
                )
            ]

        if not self.ad9912_devices_and_handles:
            self.ad9912_devices_and_handles = [
                AD9912Info(
                    self.dummy_ad9912, self.dummy_float_handle, 0.0, False, False
                )
            ]

        if not self.suservo_setters_and_info:
            self.suservo_setters_and_info = [
                SUServoSettings(
                    setter=self.dummy_suservo_frag,
                    setpoint_handle=self.dummy_float_handle,
                    shutter_present=False,
                    initial_amplitude_handle=self.dummy_float_handle,
                    frequency_handle=self.dummy_float_handle,
                )
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

        # %% Kernel invariants and variables
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "max_shutter_delay"}

        # Init these arrays to zeros - we fill it in in device_setup
        self.suservo_setpoints = [0.0] * len(self.default_suservo_beam_infos)

        self.first_run = True

    def host_setup(self):
        super().host_setup()

        # Get urukuls from the AD9910 and AD9912s
        for info in self.ad9910_devices_and_handles + self.ad9912_devices_and_handles:
            self.urukuls.append(info.device.cpld)

        # Filter out duplicates
        self.urukuls = list(set(self.urukuls))

        if not self.urukuls:
            self.urukuls = [self.dummy_urukul]

    @kernel
    def get_suservo_setpoint_by_index(self, beam_index):
        """
        Get the nominal setpoint for a given beam (allowing the user to override it)
        """
        return self.suservo_setpoints[beam_index]

    @host_only
    def get_setpoints_beaminfo_setters(self):
        """
        Get a dict of beam name -> (:class:`~SUServoedBeam` beam info, :class:`~SUServoSettings` object)
        """
        out = {}
        for beam_info, settings in zip(
            self.default_suservo_beam_infos, self.suservo_setters_and_info
        ):
            out[beam_info.name] = (beam_info, settings)
        return out

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Retrieve the values of all the generated parameters for SUServo
        # setpoints for this run of the scan. This is used only by
        # :meth:`get_suservo_setpoint_by_index`
        for i in range(len(self.suservo_setters_and_info)):
            setpoint_handle = self.suservo_setters_and_info[i].setpoint_handle
            self.suservo_setpoints[i] = setpoint_handle.get()

        # If configured to setup the AOMs automatically, do so now
        if self.automatic_setup:
            self.core.break_realtime()
            self.turn_on_all(light_enabled=self.automatic_turnon)

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
        self._set_rf_switches(light_enabled=light_enabled)

    @kernel
    def _turn_on_suservos(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_suservos")
            self.core.break_realtime()

        for i in range(len(self.suservo_setters_and_info)):
            settings = self.suservo_setters_and_info[i]
            beam_info = self.default_suservo_beam_infos[i]
            setpoint = settings.setpoint_handle.get()
            frequency = settings.frequency_handle.get()
            initial_amplitude = settings.initial_amplitude_handle.get()

            rf_switch_state = light_enabled or (
                not light_enabled and settings.shutter_present
            )

            if self.debug_mode:
                logger.info(
                    "Enabling suservo (%s)\n- beam_info %s\n- setpoint %s\n- frequency %s\n- rf_switch_state %s\n- initial_amplitude %.3f",
                    settings.setter,
                    beam_info,
                    setpoint,
                    frequency,
                    rf_switch_state,
                    initial_amplitude,
                )
                self.core.break_realtime()

            settings.setter.set_suservo(
                frequency,
                initial_amplitude,
                float(beam_info.attenuation),
                rf_switch_state=rf_switch_state,
                setpoint_v=setpoint,
                enable_iir=beam_info.servo_enabled and light_enabled,
            )

    @kernel
    def _turn_on_ad9910s(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_ad9910s")
            self.core.break_realtime()

        for info in self.ad9910_devices_and_handles:
            rf_switch_state = light_enabled or (
                not light_enabled and info.shutter_present
            )
            freq = info.frequency_handle.get()
            amp = info.amplitude_handle.get()

            info.device.set(frequency=freq, amplitude=amp)
            info.device.set_att(info.attenuation)
            if not info.has_ttl_switch:
                info.device.cfg_sw(rf_switch_state)
            # else:
            #     This will be done by _turn_on_rf_switches

            if self.debug_mode:
                logger.info(
                    "Enabling AD9910 %s, freq=%s, amp=%s", info.device, freq, amp
                )
                self.core.break_realtime()

    @kernel
    def _turn_on_ad9912s(self, light_enabled):
        if self.debug_mode:
            logger.info("SetBeamsToDefaults::_turn_on_ad9912s")
            self.core.break_realtime()

        for info in self.ad9912_devices_and_handles:
            rf_switch_state = light_enabled or (
                not light_enabled and info.shutter_present
            )
            freq = info.frequency_handle.get()

            info.device.set(frequency=freq)
            info.device.set_att(info.attenuation)

            if not info.has_ttl_switch:
                info.device.cfg_sw(rf_switch_state)
            # else:
            #     This will be done by _turn_on_rf_switches

            if self.debug_mode:
                logger.info("Enabling AD9912 %s, freq=%s", info.device, freq)
                self.core.break_realtime()

        for ttl in self.shutter_ttls:
            ttl.set_o(light_enabled)
            delay_mu(int64(self.core.ref_multiplier))

    @kernel
    def _set_rf_switches(self, light_enabled):
        for sw_withshutter in self.switch_ttls_with_shutter:
            sw_withshutter.on()
            delay_mu(int64(self.core.ref_multiplier))

        for sw_withoutshutter in self.switch_ttls_without_shutter:
            sw_withoutshutter.set_o(light_enabled)
            delay_mu(int64(self.core.ref_multiplier))
