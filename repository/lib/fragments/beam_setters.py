import logging
from typing import List
from typing import Tuple

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam


logger = logging.getLogger(__name__)


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of suservoed beams, possibly with shutters, to their default
    settings

    To use this fragment you must subclass it and provide a class attribute
    "default_beam_infos" which is a list of :class:`pyaion.models.SUServoedBeam`
    objects describing the beams that this class instance will control.

    This class will define ndscan parameters which allow the user to override
    these default settings.
    """

    default_beam_infos: List[SUServoedBeam] = None  # type: ignore

    def build_fragment(self):
        if self.default_beam_infos is None:
            raise TypeError(
                "You must create a subclass of SetBeamsToDefaults to use it - see the documentation"
            )

        self.setattr_device("core")
        self.core: Core

        self.suservo_setters_and_param_handles: List[
            Tuple[LibSetSUServoStatic, FloatParamHandle, BoolParamHandle]
        ] = []

        self.ttls: List[TTLOut] = []

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

            self.suservo_setters_and_param_handles.append((setter, setpoint_handle))

        self.max_shutter_delay = max(
            [beam_info.shutter_delay for beam_info in self.default_beam_infos]
        )

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "max_shutter_delay"}

    @portable
    def get_max_shutter_delay(self):
        return self.max_shutter_delay

    @kernel
    def turn_on_all(self, shutter_state=True):
        """
        Turn on the pre-configured beams to their default values

        If `shutter_state == False`, turn on the AOMs but turn off the shutters.

        This method does not advance the timeline and does not respect shutter
        delays - it just turns everything on immediately.

        This method advances the timeline by the time required to perform
        several suservo writes and ttl updates separated by 8mu each
        """
        if self.debug_mode:
            logger.info("SetBeamsToDefault.turn_on_all()")

        for i in range(len(self.default_beam_infos)):
            (
                setter,
                setpoint_handle,
            ) = self.suservo_setters_and_param_handles[i]
            beam_info = self.default_beam_infos[i]

            if self.debug_mode:
                logger.info("Setter (%s) - beam_info %s", setter, beam_info)

            setter.set_suservo(
                float(beam_info.frequency),
                1.0,
                float(beam_info.attenuation),
                setpoint_v=setpoint_handle.get(),
                enable_iir=beam_info.servo_enabled,
            )

        for ttl in self.ttls:
            ttl.set_o(shutter_state)
            delay_mu(8)
