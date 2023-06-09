import logging

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import kernel
from artiq.experiment import TFloat
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


class LaserStabilisationSystem(ExpFragment):
    """
    Control the laser stabilization system

    This is mainly a control Fragment designed to be used by higher-level
    Fragments. However, it also provides a :meth:`.run_once` method that sets
    the default frequencies / attenuations as defined by parameters.
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "offset_default_689_freq",
            FloatParam,
            "Default EOM offset frequency for 689 laser",
            unit="MHz",
            default=constants.OFFSET_FREQUENCY_689,
        )
        self.offset_default_689_freq: FloatParamHandle

        self.setattr_param(
            "offset_default_689_att",
            FloatParam,
            "Default EOM offset attenuation for 689 laser",
            unit="dB",
            default=constants.OFFSET_ATTENUATION_689,
        )
        self.offset_default_689_att: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        self.mirny_channel_689: ADF5356 = self.get_device("eom_cavity_offset_689")
        self.mirny_689: Mirny = self.mirny_channel_689.cpld

        self._init_completed = False

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()

        if not self._init_completed:
            self.mirny_689.init()
            self.mirny_channel_689.init()

            self._init_completed = True

        # Immediately turn on the output.
        # Do this every time to ensure that any previous offsets are undone
        self.turn_on_offset_frequency()

    @kernel
    def turn_on_offset_frequency(self):
        self.mirny_channel_689.set_frequency(self.offset_default_689_freq.get())
        self.mirny_channel_689.set_att(self.offset_default_689_att.get())

    @kernel
    def offset_689(self, offset: TFloat):
        """Offset the 689 frequency relative to its default position

        Args:
            offset (TFloat): Offset from default position
        """
        new_freq = self.offset_default_689_freq.get() + offset
        self.mirny_channel_689.set_frequency(new_freq)

    @kernel
    def run_once(self) -> None:
        # This code is not actually required - the device_setup will already do
        # this. But it's here to be explicit
        self.core.break_realtime()
        self.offset_689(0.0)


LaserStabilisationSystemExp = make_fragment_scan_exp(LaserStabilisationSystem)
