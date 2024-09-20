import logging

from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class LaserStabilisationSystem(Fragment):
    """
    Control the laser stabilization system
    """

    def build_fragment(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "This code needs fixing to not glitch the cavity sideband locks / recover from those glitches"
        )

    # def build_fragment(self):
    #     self.setattr_device("core")
    #     self.core: Core

    #     self.setattr_param(
    #         "offset_689_default_freq",
    #         FloatParam,
    #         "Default EOM offset frequency for 689 laser",
    #         unit="MHz",
    #         default=constants.OFFSET_FREQUENCY_689,
    #     )
    #     self.offset_689_default_freq: FloatParamHandle

    #     self.setattr_param(
    #         "offset_689_att",
    #         FloatParam,
    #         "Default EOM offset attenuation for 689 laser",
    #         unit="dB",
    #         default=constants.OFFSET_ATTENUATION_689,
    #     )
    #     self.offset_689_att: FloatParamHandle

    #     self.setattr_param(
    #         "rf_sw_689",
    #         BoolParam,
    #         "689 RF switch state",
    #         default="True",
    #     )
    #     self.rf_sw_689: BoolParamHandle

    # def host_setup(self):
    #     super().host_setup()

    #     self.mirny_channel_689: ADF5356 = self.get_device("mirny_eom_cavity_offset_689")
    #     self.mirny_689: Mirny = self.mirny_channel_689.cpld

    #     self._init_completed = False

    # @kernel
    # def device_setup(self):
    #     self.device_setup_subfragments()

    #     self.core.break_realtime()

    #     if not self._init_completed:
    #         self.mirny_689.init()
    #         self.mirny_channel_689.init()

    #         self._init_completed = True

    #     # Immediately turn on the output.
    #     # Do this every time to ensure that any previous offsets are undone
    #     self.mirny_channel_689.set_att(self.offset_689_att.get())
    #     self.offset_689(0.0)
    #     self.mirny_channel_689.sw.set_o(self.rf_sw_689.get())

    # @kernel
    # def offset_689(self, offset: TFloat):
    #     """Offset the 689 frequency relative to its default position

    #     Args:
    #         offset (TFloat): Offset from default position
    #     """
    #     new_freq = self.offset_689_default_freq.get() + offset
    #     self.mirny_channel_689.set_frequency(new_freq)
