import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
import numpy as np
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from repository.lib.fragments.clock_opll_controller import ClockOPLLController

from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)

from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
hbar_k = 1.05457182e-34 * 2*np.pi * constants._default_698 / 3e8

logger = logging.getLogger(__name__)

class LMTLaunchBase(DipoleTrapWithExperiment):
    """
    Implements LMT launch after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    def build_fragment(self):
        
        self.setattr_fragment("clock_opll", ClockOPLLController)
        self.clock_opll: ClockOPLLController

        self.setattr_param(
            "clock_delivery_preempt_time",
            FloatParam,
            "Preempt time before LMT pulses",
            default=constants.CLOCK_DELIVERY_PREEMPT_TIME,
            unit="us",
        )
        self.clock_delivery_preempt_time: FloatParamHandle

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
            "lmt_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during clock lmt pulse",
            default=0,
            unit="kHz",
        )
        self.lmt_pulse_aom_detuning: FloatParamHandle

        if not hasattr(self, "clock_delivery_setter"):
            self.setattr_fragment(
                "clock_delivery_setter",
                LibSetSUServoStatic,
                channel=CLOCK_BEAM_DELIVERY_INFO.suservo_device,
            )
        self.clock_delivery_setter: LibSetSUServoStatic

        self.clock_up_dds: AD9910 = self.get_device(CLOCK_UP_BEAM_INFO.urukul_device)
        self.clock_down_dds: AD9910 = self.get_device(CLOCK_DOWN_BEAM_INFO.urukul_device)

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

        # Ensure the clock up beam is set up
        if not hasattr(self, "clock_default_setter"):
            # Create the default setter for the clock beam
            # if it has not already been created
            self.setattr_fragment(
                "clock_default_setter",
                make_set_beams_to_default(
                    suservo_beam_infos=[
                        CLOCK_BEAM_DELIVERY_INFO,
                    ],
                    urukul_beam_infos=[
                        CLOCK_UP_BEAM_INFO,
                    ],
                    use_automatic_setup=True,
                    use_automatic_turnon=False,
                ),
            )
            self.clock_default_setter: SetBeamsToDefaults

            self.clock_delivery_handles = (
                self.clock_default_setter.get_setpoints_beaminfo_setters()[
                    CLOCK_BEAM_DELIVERY_INFO.name
                ][1]
            )
            self.kernel_invariants.add("clock_delivery_handles")

        # Bind the default setter's setpoint to this fragment's parameters, for
        # ease of use
        self.clock_default_setter.bind_param(
            self.clock_delivery_handles.setpoint_handle.name,
            self.spectroscopy_clock_delivery_setpoint,
        )

        #separate fragment because up beam alone is created in other mixins
        self.setattr_fragment(
            "clock_down_default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[],
                urukul_beam_infos=[
                    CLOCK_DOWN_BEAM_INFO,
                ],
                use_automatic_setup=True,
                use_automatic_turnon=False,
            ),
        )
        self.clock_down_default_setter: SetBeamsToDefaults

        # Turn the clock delivery AOM on at the start of each shot. This might
        # get overridden by e.g. slicing so we must do it again, but we want the
        # duty cycle to be 100% so the AOM settles
        class TurnOnClockDeliveryAOM(Fragment):
            def build_fragment(self, parent_frag: "LMTLaunchMixin"):
                self.parent = parent_frag

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                self.parent.core.break_realtime()
                delay(self.parent.clock_delivery_preempt_time.get())

                self.parent.prepare_clock_delivery_aom()

        self.setattr_fragment(
            "turn_on_clock_delivery_aom", TurnOnClockDeliveryAOM, self
        )

    @kernel
    def prepare_clock_delivery_aom(self):
        """
        Ensure's the clock delivery AOM is on, configured and settled. Does not
        advance the timeline and *does* write into the past.
        """
        _t_start = now_mu()
        delay(-self.clock_delivery_preempt_time.get())
        self.clock_delivery_setter.set_suservo(
            freq=self.clock_delivery_handles.frequency_handle.get()
            + self.lmt_pulse_aom_detuning.get(),
            amplitude=self.clock_delivery_handles.initial_amplitude_handle.get(),
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        at_mu(_t_start)

class LMTLaunchMixin(LMTLaunchBase):
    """
    Implements LMT launch after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    def build_fragment(self):
        super().build_fragment()
        
        self.setattr_param(
            "lmt_pulses_number",
            IntParam,
            "Number of pulses for LMT launch",
            default = 10,
        )
        self.lmt_pulses_number: IntParamHandle

        self.setattr_param(
            "lmt_pulses_duration",
            FloatParam,
            "Duration of an LMT launch pulse",
            default = 50,
            unit = "us"
        )
        self.lmt_pulse_duration: FloatParamHandle

    @kernel
    def lmt_launch(self):
        self.prepare_clock_delivery_aom()
        self.fire_lmt_pulses_pair()

    @kernel
    def fire_lmt_pulses_pair(self):

        #start ramp up
        start_ramp_time = now_mu()
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            80e6,
            80.7e6,
            wave_type=0,
        )

        #up beam pulse
        self.clock_up_dds.sw.on()
        delay(self.lmt_pulse_duration.get())
        self.clock_up_dds.sw.off()

        self.clock_opll.clock_frequency_ramper.stop_ramp()
        end_ramp_time = now_mu()

        #calculate where to start the ramp down
        up_ramp_time = self.core.mu_to_seconds(end_ramp_time-start_ramp_time)
        end_frequency = ramp_rate*up_ramp_time

        self.clock_opll.clock_OPLL_offset.set(end_frequency + hbar_k)

        #start the ramp down
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            80e6,
            end_frequency + hbar_k,
            wave_type=2,
        )

        self.clock_up_dds.sw.on()
        delay(self.lmt_pulse_duration.get())
        self.clock_up_dds.sw.off()

        self.clock_opll.clock_frequency_ramper.stop_ramp()



        



