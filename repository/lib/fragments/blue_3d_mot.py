import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants
from repository.lib.fragments.beam_setter import SetBeamsToDefaults

logger = logging.getLogger(__name__)


BLUE_3D_MOT_BEAMS = [
    "blue_push_beam",
    "blue_2dmot_A",
    "blue_2dmot_B",
    "blue_3dmot_radial",
    "blue_3dmot_axialplus",
    "blue_3dmot_axialminus",
    "blue_injection",
]


class Blue3DMOTFrag(ExpFragment):
    """
    Methods for making and controlling the blue 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("SetBeamsToDefaults", SetBeamsToDefaults, beams_to_enable=BLUE_3D_MOT_BEAMS)
        self.SetBeamsToDefaults: SetBeamsToDefaults

        # self.suservo_setters: List[LibSetSUServoStatic] = []
        # self.beam_info = [constants.AOM_BEAMS[beam] for beam in BLUE_3D_MOT_BEAMS]
        # self.ttls: List[TTLOut] = []

        # for beam, beam_info in zip(BLUE_3D_MOT_BEAMS, self.beam_info):
        #     self.setattr_fragment(beam, LibSetSUServoStatic, beam_info.suservo_device)
        #     self.suservo_setters.append(getattr(self, beam))
        #     if beam_info.shutter_device:
        #         self.ttls.append(self.get_device(beam_info.shutter_device))

        

        self.setattr_param(
            "push_beam_delay",
            FloatParam,
            "Delay between opening shutter and turning on AOM",
            default=constants.AOM_BEAMS["blue_push_beam"].shutter_delay,
            min=0,
            unit="ms",
            step=1,
        )
        self.push_beam_delay: FloatParamHandle

        self.push_beam_suservo: SUServoChannel = self.get_device(
            constants.AOM_BEAMS["blue_push_beam"].suservo_device
        )
        self.push_beam_shutter: TTLOut = self.get_device(
            constants.AOM_BEAMS["blue_push_beam"].shutter_device
        )

    @kernel
    def run_once(self):
        logger.info("Enabling all 3D MOT beams:")
        logger.info(BLUE_3D_MOT_BEAMS)

        self.core.break_realtime()
        self.enable_mot_beams()
        self.core.wait_until_mu(now_mu())

    @kernel
    def enable_mot_beams(self):
        """
        Immediately turn on all beams related to the 3D blue MOT

        This method does not advance the timeline and does not
        respect beam shutter delays - it just turns everything
        on immediately. 
        """
        self.SetBeamsToDefaults.turn_on_all()


    @kernel
    def push_beam_on(self):
        """
        Turn on the push beam using the AOM and shutter

        This method will use the AOM to turn on the beam at the cursor, having
        first disabled the AOM and opened the shutter to prevent the AOM from
        cooling down too much.

        This method does not advance the timeline, BUT will reverse time to write
        shutter opening into the past. You should therefore make sure that there
        is at least "push_beam_shutter_delay" slack, ideally with no queued RTIO
        events to prevent using a new RTIO lane.
        """

        shutter_delay_time_mu = self.core.seconds_to_mu(self.push_beam_delay.get())

        delay_mu(-shutter_delay_time_mu)

        self.push_beam_suservo.set(en_out=0, en_iir=0)
        self.push_beam_shutter.on()

        delay_mu(shutter_delay_time_mu)

        self.push_beam_suservo.set(en_out=1, en_iir=0)

    @kernel
    def push_beam_off(self):
        """
        Turn off the push beam using the AOM and shutter

        This method will turn off the beam at the cursor and then close the
        shutter and turn the AOM back on to stop it cooling down.

        This method does not advance the timeline, BUT will write shutter closing events
        into the future by "push_beam_shutter_delay" seconds.
        """

        shutter_delay_time_mu = self.core.seconds_to_mu(self.push_beam_delay.get())

        self.push_beam_suservo.set(en_out=0, en_iir=0)
        self.push_beam_shutter.off()

        delay_mu(shutter_delay_time_mu)

        self.push_beam_suservo.set(en_out=1, en_iir=0)

        delay_mu(-shutter_delay_time_mu)


Blue3DMOT = make_fragment_scan_exp(Blue3DMOTFrag)
