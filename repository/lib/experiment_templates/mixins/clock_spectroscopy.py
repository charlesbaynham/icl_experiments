import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.urukul_init import make_urukul_init

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

logger = logging.getLogger(__name__)


class ClockSpectroscopyBase(ExponentialDecayMixin, RedMOTWithExperiment):
    """
    Sets up the clock beam for clock spectroscopy (including clock shelving or interferometry)

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    """

    def build_fragment(self):
        super().build_fragment()

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
            "clock_delivery_preempt_time",
            FloatParam,
            "Preempt time before spectroscopy pulse",
            default=80e-6,
            unit="us",
        )
        self.clock_delivery_preempt_time: FloatParamHandle

        self.setattr_param(
            "clock_switch_amplitude",
            FloatParam,
            "Clock up switch AOM amplitude",
            default=CLOCK_BEAM_INFO.amplitude,
        )
        self.clock_switch_amplitude: FloatParamHandle

        self.setattr_fragment(
            "clock_delivery_setter",
            LibSetSUServoStatic,
            channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
        )
        self.clock_delivery_setter: LibSetSUServoStatic

        self.clock_dds: AD9910 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.clock_initiator = self.setattr_fragment(
            "clock_initiator", make_urukul_init([CLOCK_BEAM_INFO.urukul_device])
        )

    @kernel
    def before_start_hook_clockspec(self):
        self.core.break_realtime()

        # Setup delivery AOM. This might get overwritten by other
        # before_start_hooks but that's fine, we set it later too.
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            enable_iir=True,
        )

        # Setup switch AOM
        self.clock_dds.set_att(CLOCK_BEAM_INFO.attenuation)
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency,
            amplitude=self.clock_switch_amplitude.get(),
        )
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()


class ClockRabiSpectroscopyBase(ClockSpectroscopyBase):
    """
    Customizes ClockSpectroscopyBase for Rabi spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
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
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after spectroscopy before imaging",
            default=100e-6,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

    @kernel
    def do_rabi_spectroscopy(self):
        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time.get())
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        at_mu(_t_start)

        self.fire_clock_spec_pulse()
        delay(self.delay_after_spectroscopy.get())

    @kernel
    def fire_clock_spec_pulse(self):
        self.clock_dds.sw.on()
        delay(self.spectroscopy_pulse_time.get())
        self.clock_dds.sw.off()


class ClockRabiSpectroscopyRedMotMixin(ClockRabiSpectroscopyBase):
    """
    Uses a clock pulse for spectroscopy after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_red_mot_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.do_rabi_spectroscopy()


class ClockRabiSpectroscopyDipoleTrapMixin(
    ClockRabiSpectroscopyBase, DipoleTrapWithExperiment
):
    """
    Implements clock Rabi spectroscopy after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_rabi_spectroscopy()
