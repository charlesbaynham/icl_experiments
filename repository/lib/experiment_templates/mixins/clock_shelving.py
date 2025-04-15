import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.urukul_init import make_urukul_init

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

# from pyaion.models import SUServoedBeam
from repository.lib.fragments.pyaion_overrides.models_override import SUServoedBeam
from repository.lib.fragments.pyaion_overrides.models_override import UrukuledBeam

CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]
logger = logging.getLogger(__name__)


class ClockShelvingAndClearoutBase(RedMOTWithExperiment):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "shelving_pulse_time",
            FloatParam,
            "Length of clock shelving pulse",
            default=constants.CLOCK_SHELVING_PULSE_TIME,
            unit="us",
        )
        self.shelving_pulse_time: FloatParamHandle

        self.setattr_param(
            "shelving_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during clock shelving pulse",
            default=0,
            unit="kHz",
        )
        self.shelving_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "shelving_pulse_clearout_duration",
            FloatParam,
            "Duration of 461 clearout pulse after shelving",
            default=constants.SHELVING_PULSE_CLEAROUT_DURATION,
            unit="us",
        )
        self.shelving_pulse_clearout_duration: FloatParamHandle

        self.setattr_param(
            "clock_delivery_preempt_time_shelving",
            FloatParam,
            "Preempt time before shelving pulse",
            default=constants.CLOCK_DELIVERY_PREEMPT_TIME,
            unit="us",
        )
        self.clock_delivery_preempt_time_shelving: FloatParamHandle

        self.setattr_param(
            "shelving_clock_delivery_setpoint",
            FloatParam,
            "Setpoint for clock delivery AOM during shelving",
            default=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            min=0.0,
            unit="V",
        )
        self.shelving_clock_delivery_setpoint: FloatParamHandle

        self.setattr_fragment(
            "shelving_clock_delivery_setter",
            LibSetSUServoStatic,
            channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
        )
        self.shelving_clock_delivery_setter: LibSetSUServoStatic

        self.clock_dds: AD9912 = self.get_device(CLOCK_BEAM_INFO.urukul_device)

        # Ensure clock dds urukul is initiated
        self.shelving_initiator = self.setattr_fragment(
            "shelving_initiator", make_urukul_init([CLOCK_BEAM_INFO.urukul_device])
        )

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockshelving()

    @kernel
    def before_start_hook_clockshelving(self):
        self.core.break_realtime()

        self.shelving_clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency,
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            enable_iir=True,
        )

        self.clock_dds.set_att(CLOCK_BEAM_INFO.attenuation)
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def clock_shelving(self):
        # Prepare the clock beam
        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time_shelving.get())
        self.shelving_clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.shelving_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.shelving_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        at_mu(_t_start)

        delay_mu(int64(self.core.ref_multiplier))
        self.clock_dds.set(frequency=CLOCK_BEAM_INFO.frequency)
        delay_mu(int64(self.core.ref_multiplier))

        # Pulse it onto the atoms
        self.clock_dds.sw.on()
        delay(self.shelving_pulse_time.get())
        self.clock_dds.sw.off()

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.shelving_pulse_clearout_duration.get(),
            ignore_final_shutters=True,
        )


class ClockShelvingAndClearoutRedMOTMixin(ClockShelvingAndClearoutBase):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_shelving()


class ClockShelvingAndClearoutDipoleTrapMixin(
    ClockShelvingAndClearoutBase, DipoleTrapWithExperiment
):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_dipole_trap_hook`
    """

    @kernel
    def post_dipole_trap_hook(self):
        self.post_dipole_trap_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_shelving()
