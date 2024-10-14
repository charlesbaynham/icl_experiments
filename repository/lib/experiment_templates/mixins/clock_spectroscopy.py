import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.urukul_init import make_urukul_init
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.pyaion_overrides.suservo_override import (
    LibSetSUServoStatic,
)

CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

logger = logging.getLogger(__name__)


class ClockSpectroscopyMixin(RedMOTWithExperiment):
    """
    Uses a clock pulse for spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_red_mot_hook`
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
            "Frequency detuning of delivery AOM during spectroscopy pulse",
            default=0,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "spectroscopy_clock_delivery_setpoint",
            FloatParam,
            "Setpoint for clock delivery AOM",
            default=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            min=0.0,
            unit="V",
        )
        self.spectroscopy_clock_delivery_setpoint: FloatParamHandle

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=1e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

        self.setattr_fragment(
            "clock_delivery_setter",
            LibSetSUServoStatic,
            channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
        )
        self.clock_delivery_setter: LibSetSUServoStatic

        self.clock_dds: AD9912 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.clock_initiator = self.setattr_fragment(
            "clock_initiator", make_urukul_init([CLOCK_BEAM_INFO.urukul_device])
        )

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()

    @kernel
    def before_start_hook_clockspec(self):
        self.core.break_realtime()

        # Setup delivery AOM
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )

        # Setup switch AOM
        self.clock_dds.set_att(CLOCK_BEAM_INFO.attenuation)
        self.clock_dds.set(frequency=CLOCK_BEAM_INFO.frequency)
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )

        self.clock_dds.sw.on()
        delay(self.spectroscopy_pulse_time.get())
        self.clock_dds.sw.off()

    @kernel
    def do_first_pulse(self, andor_exposure):
        self.do_pulse(andor_exposure)
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
