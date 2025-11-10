import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import AD9910
from artiq.language import kernel
from ndscan.experiment import Fragment
from pyaion.fragments.urukul_init import make_urukul_init
import repository.lib.constants as constants
from repository.lib.fragments.painted_pulse import (
    DiffractionCompensatedQuadraticShapedPulse,
)

PAINTING_URUKUL_CHANNEL = "urukul9910_aom_1064_painting"

class DipolePainterController(Fragment):
    """
    A fragment which will control the dipole painter beam
    """
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # Initiate the Urukul for this channel
        self.setattr_fragment(
            "urukul_init", make_urukul_init([PAINTING_URUKUL_CHANNEL])
        )

        self.dds: AD9910 = self.get_device(PAINTING_URUKUL_CHANNEL)

        # Create the painter fragment which will control the painting AOM 
        self.setattr_fragment(
            "painter",
            DiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=PAINTING_URUKUL_CHANNEL,
        )

        self.painter: DiffractionCompensatedQuadraticShapedPulse

    @kernel
    def turn_painter_on(self):
        """
        Goes through the motion of switching the painter AOM on 
        """
        self.core.break_realtime()
        self.dds.sw.off()

        # This is an arbitrary frequency - it will be overwritten by the pulse
        self.dds.set(frequency=10e6, amplitude=0.1)
        # Default value perhaps...
        self.dds.set_att(10.0)
        self.core.break_realtime()
        self.painter.start_output()

    @kernel
    def turn_painter_off(self):
        """
        Switch the painter off 
        """
        self.painter.stop_output()
    
