import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language.core import delay
from artiq.language.core import delay_mu
from artiq.language.core import kernel
from artiq.language.core import now_mu
from artiq.language.core import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from numpy import int64

from repository.lib import constants
from repository.lib.fragments.relock_falc_toptica import RelockFALCWithWavemeterFrag

logger = logging.getLogger(__name__)


class Relock698Frag(RelockFALCWithWavemeterFrag, ExpFragment):
    """
    Relock the 698 to the laser stabilization cavity

    For the 698, this is straightforward
    """

    laser_name_wand = "Sirah"
    laser_name_devicedb = "toptica_698"

    def run_once(self) -> None:
        self.relock()


class Control689Shutters(Fragment):
    """
    Provide a method for using the 689 vs. 1379 wavemeter multiplexing shutters
    """

    def build_fragment(self):
        # Get the shutters for the 689 & 1379 wavemeter multiplexing
        self.setattr_device("ttl_shutter_red_wavemeter_689_master")
        self.setattr_device("ttl_shutter_red_wavemeter_689_from_1379")

        self.ttl_shutter_red_wavemeter_689_master: TTLOut
        self.ttl_shutter_red_wavemeter_689_from_1379: TTLOut

        self.setattr_device("core")
        self.core: Core

    @kernel
    def set_shutters(self, open_689: bool = True, open_1379: bool = True) -> None:
        """
        Control the shutters for the wavemeter multiplexing.

        These shutters need to be left open in the end, otherwise the 1379 lock
        will not work!

        Args:
            open_689 (bool, optional): Defaults to True.
            open_1379 (bool, optional): Defaults to True.
        """
        self.core.break_realtime()
        self.ttl_shutter_red_wavemeter_689_from_1379.set_o(open_1379)
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_shutter_red_wavemeter_689_master.set_o(open_689)

        delay(constants.WAND_SHUTTERS_DELAY)  # Wait for closing time

        self.core.wait_until_mu(now_mu())


class Relock689Frag(RelockFALCWithWavemeterFrag, ExpFragment):
    """
    Relock the 689 master to the laser stabilization cavity

    To do this, we must handle the shutters for the 689 & 1379 wavemeter
    multiplexing. This will involve blocking the 1379 light, unlocking its PLL.
    So this will need to be relocked next: see :class:`~.Relock1379Frag`.
    """

    laser_name_wand = "689"
    laser_name_devicedb = "toptica_689"

    def build_fragment(self):
        super().build_fragment()

        # Add control of the shutters for the 689 / 1379 wavemeter
        self.setattr_fragment("shutter_control", Control689Shutters)
        self.shutter_control: Control689Shutters

        # The shutters are controlled through the core, so we'll need kernels
        self.setattr_device("core")
        self.core: Core

    @rpc(flags={"sync"})
    def relock_RPC(self):
        """Call the original relock() method on the host, via an RPC"""
        return super().relock()

    @kernel
    def relock(self) -> None:
        """
        Redefine relock() so that it's now a kernel method that calls the host relock via RPC
        """
        self.shutter_control.set_shutters(open_689=True, open_1379=False)
        try:
            self.relock_RPC()
        finally:
            self.shutter_control.set_shutters(open_689=True, open_1379=True)

    @kernel
    def run_once(self) -> None:
        self.relock()


class Relock1379Frag(Control689Shutters, ExpFragment):
    """
    Relock the 1379  to the doubled 689 PLL

    Change the WAND exposures before doing the relock, but be sure to change
    them back afterwards
    """

    laser_name_wand = "689"  # We use the same WAND channel as the 689, but multiplex with the shutters
    laser_name_devicedb = "toptica_1379"  # TODO: This is a problem. The WAND steer is still steering the 689 piezo, not the 1379. Obvious in hindsight. Will need to deal with.

    def run_once(self) -> None:
        raise NotImplementedError("This does not work yet. See the comment above")

        self.set_shutters(open_689=False, open_1379=True)

        initial_exposures = self.wand_server.get_laser_db()[self.laser_name_wand][
            "exposure"
        ]

        try:
            self.relock()
        finally:
            for i, ex in enumerate(initial_exposures):
                logger.info(
                    "Resetting %s exposure to %f, %d", self.laser_name_wand, ex, i
                )
                self.wand_server.set_exposure(self.laser_name_wand, ex, i)
            self.set_shutters(open_689=True, open_1379=True)
