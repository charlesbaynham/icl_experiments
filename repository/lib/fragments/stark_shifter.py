import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

import repository.lib.constants as constants
from repository.lib import constants

logger = logging.getLogger(__name__)


class StarkShifter(Fragment):
    """
    Prepares the Stark shifting beam and provides methods for Stark shifting the
    atoms

    Provides the :meth:`~.do_stark_pulse()` method to apply a shifting pulse.
    """

    def build_fragment(self):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        self.setattr_device("core")
        self.core: Core

        ### Fragments ###

        # Setup the default DDS settings for the switch and delivery AOMs
        self.setattr_fragment(
            "set_defaults_delivery",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["stark_shifter_689_delivery"]
                ],
                name="StarkDeliverySetter",
                use_automatic_setup=False,
                use_automatic_turnon=False,
            ),
        )
        self.setattr_fragment(
            "set_defaults_switch",
            make_set_beams_to_default(
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["stark_shifter_689_switch"]
                ],
                name="StarkSwitchSetter",
                use_automatic_setup=False,
                use_automatic_turnon=False,
            ),
        )

        self.set_defaults_delivery: SetBeamsToDefaults
        self.set_defaults_switch: SetBeamsToDefaults

        ### Parameters ###

        self.setattr_param(
            "stark_pulse_duration",
            FloatParam,
            "Duration of Stark shifting pulse",
            default=constants.DURATION_OF_STARK_PULSE,
            unit="us",
        )
        self.stark_pulse_duration: FloatParamHandle

    def host_setup(self):
        ### Devices ###

        # Get direct control of the Stark switching AOM's switch
        self.stark_689_dds_rf_switch: TTLOut = self.get_device(
            constants.URUKULED_BEAMS["stark_shifter_689_switch"].urukul_device
        ).sw
        self.kernel_invariants.add("stark_689_dds_rf_switch")

        return super().host_setup()

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Turn the Stark shift delivery AOM on and the switch AOM off
        # TODO are we sure this doesn't affect the dipole trap?
        self.core.break_realtime()
        self.set_defaults_delivery.turn_on_all(light_enabled=True)
        self.core.break_realtime()
        self.set_defaults_switch.turn_on_all(light_enabled=False)

        self.stark_689_dds_rf_switch.off()

    @kernel
    def do_stark_pulse(self):
        """
        Do a Stark shifting pulse for the duration specified by `stark_pulse_duration`.

        Advances the timeline by `stark_pulse_duration`.
        """
        self.stark_689_dds_rf_switch.pulse(self.stark_pulse_duration.get())
