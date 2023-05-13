import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ns
from ndscan.experiment import Fragment
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


class ControlBeamsWithoutCoolingAOM(Fragment):
    """
    Methods to turn on/off a list of beams using a SUServoed AOM for sharp
    edges and a shutter to fully block it

    The AOMs will be left on as much as possible even while the beams are off
    (but blocked with the shutter) to avoid pointing instability from thermal
    effects.

    Note that when groups of beams are intended to be turned on together, you
    should use a sincle instance of this fragment to control all of them rather
    than initialising one for each beam. That's because this fragment skips
    forwards and backwards in time and will therefore wantonly consume RTIO
    lanes unless you let it reduce this behaviour by knowing in advance which
    shutters need to be opened.
    """

    def build_fragment(self, beam_infos: List[constants.SUServoedBeam]):
        logger.debug("Building with %s", beam_infos)
        self.beam_infos = beam_infos

        self.setattr_device("core")
        self.core: Core

        self.beam_suservos: List[SUServoChannel] = []
        self.beam_shutters: List[TTLOut] = []
        self.beam_delays: List[float] = []

        for beam_info in beam_infos:
            if beam_info.shutter_device is None:
                raise ValueError(
                    "Beam [%s] has no shutter configured".format(beam_info.name)
                )

            self.beam_suservos.append(self.get_device(beam_info.suservo_device))
            self.beam_shutters.append(self.get_device(beam_info.shutter_device))
            self.beam_delays.append(beam_info.shutter_delay)

        # Sort beams by order of delay - smallest delay first
        tupled = list(zip(self.beam_suservos, self.beam_shutters, self.beam_delays))

        logger.debug("tupled = %s", tupled)
        logger.debug("tupled[0] = %s", tupled[0])

        sorted_tupled = sorted(tupled, key=lambda v: v[2])
        self.beam_suservos, self.beam_shutters, self.beam_delays = zip(*sorted_tupled)

        # Convert them back to lists - python has turned them into tuples
        self.beam_suservos = list(self.beam_suservos)
        self.beam_shutters = list(self.beam_shutters)
        self.beam_delays = list(self.beam_delays)

        logger.debug("sorted_tupled = %s", sorted_tupled)

    @kernel
    def turn_beams_on(self):
        """
        Turn on the beams using the AOM and shutter

        This method will use the AOM to turn on the beam at the cursor, having
        first disabled the AOM and opened the shutter to prevent the AOM from
        cooling down too much.

        Start with the shutters with the longest delay to avoid switching
        backwards and forwards in time

        This method advances the timelines by 30ns per beam, BUT will reverse time to
        write shutter opening into the past. You should therefore make sure that
        there is at least "shutter_delay_time" slack, ideally with no queued
        RTIO events to prevent using a new RTIO lane.
        """

        for i in range(len(self.beam_delays) - 1, -1, -1):
            suservo = self.beam_suservos[i]
            shutter = self.beam_shutters[i]
            delay_by = self.beam_delays[i]

            delay(-delay_by)

            suservo.set(en_out=0, en_iir=0)
            delay(10 * ns)
            shutter.on()
            delay(10 * ns)

            delay(delay_by)

        for i in range(len(self.beam_delays) - 1, -1, -1):
            suservo = self.beam_suservos[i]
            shutter = self.beam_shutters[i]
            delay_by = self.beam_delays[i]

            suservo.set(en_out=1, en_iir=0)

            delay(10 * ns)

    @kernel
    def turn_beams_off(self):
        """
        Turn off the beams using the AOM and shutter

        This method will turn off the beam at the cursor and then close the
        shutter and turn the AOM back on to stop it cooling down.

        This method will advance the timeline by 30ns per beam BUT will write
        shutter closing events into the future by "shutter_delay_time" seconds.
        """

        for i in range(len(self.beam_delays)):
            suservo = self.beam_suservos[i]
            shutter = self.beam_shutters[i]
            delay_by = self.beam_delays[i]

            suservo.set(en_out=0, en_iir=0)
            delay(10 * ns)
            shutter.off()
            delay(10 * ns)

        for i in range(len(self.beam_delays)):
            suservo = self.beam_suservos[i]
            shutter = self.beam_shutters[i]
            delay_by = self.beam_delays[i]

            delay(delay_by)

            suservo.set(en_out=1, en_iir=0)
            delay(10 * ns)

            delay(-delay_by)
