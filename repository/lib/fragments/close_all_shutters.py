from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from numpy import int64

from repository.lib.constants import AOM_BEAMS


class CloseAllShutters(Fragment):
    """
    Close all shutters for given beams

    This Fragment must be the first subfragment added using
    :meth:`~setattr_subfragment`, otherwise it'll close the shutters durnig
    device_setup after other fragments have acted, potentially changing their
    behaviour.
    """

    ttl_shutters: List[str] = None

    def build_fragment(self) -> None:
        if self.ttl_shutters is None:
            raise NotImplementedError(
                "You must subclass this fragment to specify which shutters you'd like to close"
            )

        if self.ttl_shutters is []:
            raise NotImplementedError("Empty lists are not supported")

        self.setattr_device("core")
        self.core: Core

        self.ttls: List[TTLOut] = []
        for ttl_name in self.ttl_shutters:
            self.ttls.append(self.get_device(ttl_name))

        self.first_run = True

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            self.first_run = False
            self.core.break_realtime()

            for ttl in self.ttls:
                ttl.off()
                delay_mu(int64(self.core.ref_multiplier))

        self.device_setup_subfragments()


class CloseAllICLShutters(CloseAllShutters):
    ttl_shutters = [
        info.shutter_device for info in AOM_BEAMS.values() if info.shutter_device
    ]
