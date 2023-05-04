import logging
from typing import List

from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


BLUE_SHUTTERS = [
    "TTL_shutter_461_pushbeam",
    "TTL_shutter_461_2dmot_is_it_a",
    "TTL_shutter_461_IJD1_is_it_b",
    "TTL_shutter_461_3dmot",
    "TTL_shutter_679_temporary_shutter",
    "TTL_shutter_707_temporary_shutter",
]


class HackBlueSystemOn(ExpFragment):
    """
    Hack the blue AOMs on
    """

    def build_fragment(self):
        self.setattr_fragment(
            "suservo_aom_doublepass_461_injection",
            LibSetSUServoStatic,
            "suservo_aom_doublepass_461_injection",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_spectroscopy",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_spectroscopy",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_pushbeam",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_pushbeam",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_2dmot_a",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_2dmot_a",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_2dmot_b",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_2dmot_b",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_3DMOT_radial",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_3DMOT_radial",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_3DMOT_axialplus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_3DMOT_axialplus",
        )
        self.setattr_fragment(
            "suservo_aom_singlepass_461_3DMOT_axialminus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_3DMOT_axialminus",
        )

        self.setattr_device("core")

        self.ttls = [self.get_device(ttl) for ttl in BLUE_SHUTTERS]
        self.ttls: List[TTLOut]

    @kernel
    def run_once(self):
        # Set the outputs
        self.suservo_aom_doublepass_461_injection.set_suservo(
            constants.BLUE_INJECTION_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_INJECTION_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_spectroscopy.set_suservo(
            constants.BLUE_PROBE_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_PROBE_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_pushbeam.set_suservo(
            constants.BLUE_PUSHBEAM_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_PUSHBEAM_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_2dmot_a.set_suservo(
            constants.BLUE_2DMOT_A_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_2DMOT_A_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_2dmot_b.set_suservo(
            constants.BLUE_2DMOT_B_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_2DMOT_B_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_3DMOT_radial.set_suservo(
            constants.BLUE_3DMOT_RADIAL_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_3DMOT_RADIAL_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_3DMOT_axialplus.set_suservo(
            constants.BLUE_3DMOT_AXIALPLUS_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_3DMOT_AXIALPLUS_AOM_ATTENUATION,
        )

        self.suservo_aom_singlepass_461_3DMOT_axialminus.set_suservo(
            constants.BLUE_3DMOT_AXIALMINUS_AOM_DEFAULT_FREQUENCY,
            1.0,
            constants.BLUE_3DMOT_AXIALMINUS_AOM_ATTENUATION,
        )

        for ttl in self.ttls:
            ttl.on()


HackBlueSystemOnExp = make_fragment_scan_exp(HackBlueSystemOn)
