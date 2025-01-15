import logging

from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.urukul_init import make_urukul_init
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

logger = logging.getLogger(__name__)


class ClockSpectroscopyBaseFrag(RedMOTCheckpoints):
    """
    Sets up the clock beam for clock spectroscopy (including clock shelving or
    interferometry)
    """

    def build_fragment(self, blue_3d_mot: Blue3DMOTFrag):
        self.setattr_device("core")
        self.core: Core

        self.blue_3d_mot = blue_3d_mot
        self.kernel_invariants.add("blue_3d_mot")

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

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Set up the delivery AOM. This might get overwritten by other
        # fragments but that's fine, we set it later too.
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            enable_iir=True,
        )

        # Set up the switch AOM
        self.clock_dds.set_att(CLOCK_BEAM_INFO.attenuation)
        self.clock_dds.set(frequency=CLOCK_BEAM_INFO.frequency)
        self.clock_dds.sw.off()
        self.clock_dds.cfg_sw(False)

    @kernel
    def after_first_imaging_pulse_checkpoint(self):
        """
        After the first imaging pulse, repump the clock state
        """
        self.after_first_imaging_pulse_checkpoint_subfragments()

        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()


class _ClockRabiSpectroscopyMixinBase(RedMOTWithExperiment):
    """
    Base mixin for Rabi clock spectroscopy, providing
    :meth:`~do_rabi_spectroscopy`

    Defines and uses a customized ClockSpectroscopyBaseFrag as a subfragment.

    Kernel hooks used (multiple mixins cannot use the same hooks):

        * :meth:`~do_experiment_after_red_mot_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        class ClockRabiSpectroscopyFrag(ClockSpectroscopyBaseFrag):
            def build_fragment(self, blue_3d_mot: Blue3DMOTFrag):
                super().build_fragment(blue_3d_mot=blue_3d_mot)

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

                self.clock_dds.sw.on()
                delay(self.spectroscopy_pulse_time.get())
                self.clock_dds.sw.off()
                delay(self.delay_after_spectroscopy.get())

        self.setattr_fragment(
            "clock_rabi_spectroscopy",
            ClockRabiSpectroscopyFrag,
            blue_3d_mot=self.blue_3d_mot,
        )
        self.clock_rabi_spectroscopy: ClockRabiSpectroscopyFrag

        # Expose the most important parameters
        self.setattr_param_rebind(
            "spectroscopy_pulse_time", self.clock_rabi_spectroscopy
        )
        self.setattr_param_rebind(
            "spectroscopy_pulse_aom_detuning", self.clock_rabi_spectroscopy
        )
        self.setattr_param_rebind(
            "spectroscopy_clock_delivery_setpoint", self.clock_rabi_spectroscopy
        )


class ClockRabiSpectroscopyRedMotMixin(_ClockRabiSpectroscopyMixinBase):
    """
    Uses a clock pulse for Rabi spectroscopy after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_red_mot_hook`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.clock_rabi_spectroscopy.do_rabi_spectroscopy()


class ClockRabiSpectroscopyDipoleTrapMixin(
    _ClockRabiSpectroscopyMixinBase, DipoleTrapWithExperiment
):
    """
    Uses a clock pulse for Rabi spectroscopy after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.clock_rabi_spectroscopy.do_rabi_spectroscopy()
