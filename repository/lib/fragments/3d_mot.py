import logging
from typing import List

from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


BLUE_SHUTTERS = [
    "TTL_shutter_461_pushbeam",
    "TTL_shutter_461_2dmot_is_it_a",
    "TTL_shutter_461_2dmot_is_it_b",
    "TTL_shutter_461_3dmot",
    "TTL_shutter_679_temporary_shutter",
    "TTL_shutter_707_temporary_shutter",
]


class Blue3DMOT(Fragment):
    """
    Make a 3D MOT

    This Fragment exposes functions for making and interacting with the 3D blue MOT
    """

    def build_fragment(self):
        pass
