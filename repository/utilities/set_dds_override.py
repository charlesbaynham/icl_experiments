import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.experiment import EnumerationValue
from artiq.language import kernel
from artiq.master.worker_db import DummyDevice
from ndscan.experiment.entry_point import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.lib.utils import get_local_devices

from repository.lib import constants

logger = logging.getLogger(__name__)


class SetDDSOverrideFrag(ExpFragment):
    """
    Set an AD9910 or AD9912 DDS channel, while setting all other channels on this Urukul to their defaults
    """

    def build_fragment(self):
        list_of_channels = get_local_devices(self, AD9910) + get_local_devices(
            self, AD9912
        )
        logger.debug(
            "Found %d DDS channels: %s", len(list_of_channels), list_of_channels
        )

        self.setattr_argument(
            "device_name",
            EnumerationValue(list_of_channels, default=list_of_channels[0]),
        )
        self.device_name: str

        self.setattr_param(
            "frequency",
            FloatParam,
            description="DDS frequency",
            default=100e6,
            unit="MHz",
        )
        self.frequency: FloatParamHandle

        self.setattr_param(
            "attenuation",
            FloatParam,
            description="Output attenuation",
            default=30.0,
            min=0.0,
            max=30.0,
            unit="dB",
        )
        self.attenuation: FloatParamHandle

        self.setattr_param(
            "switch",
            BoolParam,
            description="RF switch state",
            default=True,
        )
        self.switch: BoolParamHandle

        self.setattr_device("core")
        self.core: Core

        # If we are in param-scanning mode, stop here
        if isinstance(self.core, DummyDevice):
            logger.debug(
                "Running in param-scanning mode, skipping device initialization"
            )
            return

        # Get the chosen channel
        self.channel: AD9912 = self.get_device(self.device_name)
        logger.info("Selected DDS channel: %s", self.device_name)

        # Get description of this channel
        channel_desc = self.get_device_db()[self.device_name]

        # Resolve any aliases
        while isinstance(channel_desc, str):
            channel_desc = self.get_device_db()[channel_desc]

        logger.debug("Channel description: %s", channel_desc)
        logger.debug("CPLD device: %s", channel_desc["arguments"]["cpld_device"])

        # Get all the channels that share the same Urukul
        self.urukul_channels = [
            k
            for k, v in self.get_device_db().items()
            if (
                "module" in v
                and "class" in v
                and "arguments" in v
                and v["module"] == channel_desc["module"]
                and v["class"] == channel_desc["class"]
                and v["arguments"]["cpld_device"]
                == channel_desc["arguments"]["cpld_device"]
            )
        ]
        logger.info(
            "Found %d channels on the same Urukul CPLD: %s",
            len(self.urukul_channels),
            self.urukul_channels,
        )

        # Get DDS objects for each
        self.urukul_channel_objs = [
            self.get_device(chan_name) for chan_name in self.urukul_channels
        ]

        # Look up if any of these channels are used in URUKULED_BEAMS
        self.related_beam_infos = [
            v
            for k, v in constants.URUKULED_BEAMS.items()
            if self.get_device(v.urukul_device) in self.urukul_channel_objs
        ]

        if self.related_beam_infos:
            beam_names = [beam.name for beam in self.related_beam_infos]
            logger.info(
                "Found %d related beams to initialize: %s",
                len(self.related_beam_infos),
                beam_names,
            )
        else:
            logger.info("No related beams found in URUKULED_BEAMS for this Urukul")

        # If we have related beams, create a default beam setter for them
        if self.related_beam_infos:
            logger.debug(
                "Creating default beam setter with automatic setup and turn-on"
            )
            self.setattr_fragment(
                "default_beam_setter",
                make_set_beams_to_default(
                    suservo_beam_infos=[],
                    urukul_beam_infos=self.related_beam_infos,
                    use_automatic_setup=True,
                    use_automatic_turnon=True,
                ),
            )
            self.default_beam_setter: SetBeamsToDefaults

    @kernel
    def device_setup(self):
        self.core.break_realtime()

        self.channel.cpld.init()
        self.channel.init()

        self.device_setup_subfragments()

    def host_setup(self):
        """Called before device_setup on the host side."""
        super().host_setup()
        logger.info(
            "Setting up DDS override: frequency=%.3f MHz, attenuation=%.1f dB, switch=%s",
            self.frequency.get() * 1e-6,
            self.attenuation.get(),
            self.switch.get(),
        )

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.channel.sw.set_o(self.switch.get())
        self.channel.set(self.frequency.get())
        self.channel.set_att(self.attenuation.get())


SetDDSOverride = make_fragment_scan_exp(SetDDSOverrideFrag)
