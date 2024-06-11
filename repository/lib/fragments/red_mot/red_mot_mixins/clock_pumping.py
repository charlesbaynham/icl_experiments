import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.urukul_init import make_urukul_init
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]

logger = logging.getLogger(__name__)


class ClockPumpingMixin(RedMOTWithExperiment):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_spectroscopy_hook`
    * :meth:`~do_first_pulse`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "pumping_pulse_time",
            FloatParam,
            "Length of clock pumping pulse",
            default=50e-6,
            unit="us",
        )
        self.pumping_pulse_time: FloatParamHandle

        self.setattr_param(
            "pumping_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during clock pumping pulse",
            default=0,
            unit="kHz",
        )
        self.pumping_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "pumping_pulse_clearout_duration",
            FloatParam,
            "Duration of 461 clearout pulse after pumping",
            default=500e-6,
            unit="us",
        )
        self.pumping_pulse_clearout_duration: FloatParamHandle

        # TODO: Reinstate clock beam amplitude control when we have it!
        # self.setattr_param(
        #     "spectroscopy_pulse_aom_amplitude",
        #     FloatParam,
        #     "Amplitude of delivery AOM during spectroscopy pulse. SUServoing is disabled",
        #     default=1.0,
        #     min=0.0,
        #     max=1.0,
        # )
        # self.spectroscopy_pulse_aom_amplitude: FloatParamHandle

        self.clock_dds: AD9912 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.pumping_initiator = self.setattr_fragment(
            "pumping_initiator", make_urukul_init([CLOCK_BEAM_INFO.urukul_device])
        )

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockpumping()

    @kernel
    def before_start_hook_clockpumping(self):
        self.core.break_realtime()

        self.clock_dds.set_att(CLOCK_BEAM_INFO.attenuation)
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def pre_expansion_hook(self):
        # Prepare the clock beam
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency + self.pumping_pulse_aom_detuning.get()
        )

        # Pulse it onto the atoms
        self.clock_dds.sw.on()
        delay(self.pumping_pulse_time.get())
        self.clock_dds.sw.off()

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.pumping_pulse_clearout_duration.get()
        )
