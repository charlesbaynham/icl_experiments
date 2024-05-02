import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.fragments.beams.urukul_init import make_urukul_init
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]

logger = logging.getLogger(__name__)


class ClockSpectroscopyMixin(RedMOTWithExperiment):
    """
    Uses a clock pulse for spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_spectroscopy_hook`
    * :meth:`~do_first_pulse`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=50e-6,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during spectroscopy pulse",
            default=0,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

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

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=1e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

        self.clock_dds: AD9912 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.clock_initiator = self.setattr_fragment(
            "clock_initiator", make_urukul_init([CLOCK_BEAM_INFO.urukul_device])
        )

    @kernel
    def before_start_hook(self):
        self.core.break_realtime()

        self.clock_dds.set(frequency=CLOCK_BEAM_INFO.frequency)
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def do_spectroscopy_hook(self):
        self.clock_dds.sw.on()
        delay(self.spectroscopy_pulse_time.get())
        self.clock_dds.sw.off()

    @kernel
    def do_first_pulse(self, andor_exposure):
        self._do_pulse(andor_exposure)
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
