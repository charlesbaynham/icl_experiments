import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


class SetBeamsToDefaults(Fragment):
    """
    Turn on a list of suservoed beams, possibly with shutters, to their default settings
    """

    def build_fragment(self, beams_to_enable: List[str]):
        self.beams_to_enable = beams_to_enable

        self.setattr_device("core")
        self.core: Core

        self.suservo_setters: List[LibSetSUServoStatic] = []
        self.beam_info = [constants.AOM_BEAMS[beam] for beam in self.beams_to_enable]
        self.ttls: List[TTLOut] = []

        for beam, beam_info in zip(self.beams_to_enable, self.beam_info):
            self.setattr_fragment(beam, LibSetSUServoStatic, beam_info.suservo_device)
            self.suservo_setters.append(getattr(self, beam))
            if beam_info.shutter_device:
                self.ttls.append(self.get_device(beam_info.shutter_device))

        self.setattr_device("core")

    @kernel
    def turn_on_all(self):
        """
        Turn on the pre-configured beams to their default values

        This method does not advance the timeline and does not respect
        shutter delays - it just turns everything on immediately.
        """
        for i in range(len(self.beams_to_enable)):
            setter = self.suservo_setters[i]
            beam_info = self.beam_info[i]

            setter.set_suservo(
                float(beam_info.frequency), 1.0, float(beam_info.attenuation)
            )

        for ttl in self.ttls:
            ttl.on()


class ControlBeamWithoutCoolingAOM(Fragment):
    """
    Methods to turn on/off a beam using a SUServoed AOM for sharp edges
    and a shutter to fully block it

    The AOM will be left on as much as possible even while the beam is
    off (but blocked with the shutter) to avoid pointing instability
    from thermal effects.
    """

    def build_fragment(self, beam_info: constants.SUServoedBeam):
        self.beam_info = beam_info

        if beam_info.shutter_device is None:
            raise ValueError("Beam [%s] has no shutter configured".format(beam_info))

        self.setattr_device("core")
        self.core: Core

        # Allow the user to override the beam delay if they wish
        self.setattr_param(
            "beam_delay",
            FloatParam,
            "Delay between opening shutter and turning on AOM",
            default=beam_info.shutter_delay,
            min=0,
            unit="ms",
            step=1,
        )
        self.beam_delay: FloatParamHandle

        self.beam_suservo: SUServoChannel = self.get_device(
            constants.AOM_BEAMS["blue_push_beam"].suservo_device
        )
        self.beam_shutter: TTLOut = self.get_device(
            constants.AOM_BEAMS["blue_push_beam"].shutter_device
        )

    @kernel
    def turn_beam_on(self):
        """
        Turn on the beam using the AOM and shutter

        This method will use the AOM to turn on the beam at the cursor, having
        first disabled the AOM and opened the shutter to prevent the AOM from
        cooling down too much.

        This method does not advance the timeline, BUT will reverse time to write
        shutter opening into the past. You should therefore make sure that there
        is at least "shutter_delay_time" slack, ideally with no queued RTIO
        events to prevent using a new RTIO lane.
        """

        delay(-self.beam_delay.get())

        self.beam_suservo.set(en_out=0, en_iir=0)
        self.beam_shutter.on()

        delay(self.beam_delay.get())

        self.beam_suservo.set(en_out=1, en_iir=0)

    @kernel
    def turn_beam_off(self):
        """
        Turn off the beam using the AOM and shutter

        This method will turn off the beam at the cursor and then close the
        shutter and turn the AOM back on to stop it cooling down.

        This method does not advance the timeline, BUT will write shutter closing events
        into the future by "shutter_delay_time" seconds.
        """

        self.beam_suservo.set(en_out=0, en_iir=0)
        self.beam_shutter.off()

        delay(self.beam_delay.get())

        self.beam_suservo.set(en_out=1, en_iir=0)

        delay(-self.beam_delay.get())
