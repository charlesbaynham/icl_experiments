import logging

from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults

from repository.lib import constants
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

logger = logging.getLogger(__name__)

from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    add_spectroscopy_params,
)


class _UpBeamInterferometryFrag(RedMOTCheckpoints):
    def build_fragment(self):
        add_spectroscopy_params(self)

        self.setattr_device("core")

        class _UpBeamSetter(SetBeamsToDefaults):
            default_suservo_beam_infos = [constants.SUSERVOED_BEAMS["red_up"]]

        # Configure up beam with default settings
        self.setattr_fragment("up_beam_default_setter", _UpBeamSetter)
        self.up_beam_default_setter: SetBeamsToDefaults

        # Get direct access to the SUServo channel
        self.setattr_device("suservo_aom_singlepass_689_up")
        self.suservo_aom_singlepass_689_up: SUServoChannel

        self.setattr_param(
            "delay_between_interferometry_pulses",
            FloatParam,
            "Delay between interferometry pulses",
            default=100e-9,
            unit="us",
        )
        self.delay_between_interferometry_pulses: FloatParamHandle

        self.setattr_param(
            "phase_step",
            FloatParam,
            "Phase step in interferometry sequence",
            default=0.0,
        )
        self.phase_step: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        # Kernel vars
        self.suservo_freq = constants.SUSERVOED_BEAMS["red_up"].frequency
        # Allow negative phases up to -10
        self.phase_constant = 10.0

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Enable the Up beam with default settings, but turn off the AOM and open the shutter
        self.core.break_realtime()
        self.up_beam_default_setter.turn_on_all(light_enabled=True)

        # Set up SUServo profiles manually with config options for different phases
        self.suservo_aom_singlepass_689_up.set_dds(
            0, frequency=self.suservo_freq, offset=0.0, phase=self.phase_constant
        )
        self.suservo_aom_singlepass_689_up.set_dds(
            1,
            frequency=self.suservo_freq,
            offset=0.0,
            phase=self.phase_constant + 1.0 * self.phase_step.get(),
        )
        self.suservo_aom_singlepass_689_up.set_dds(
            2,
            frequency=self.suservo_freq,
            offset=0.0,
            phase=self.phase_constant + 4.0 * self.phase_step.get(),
        )

        for i in range(3):
            self.suservo_aom_singlepass_689_up.set_y(
                profile=i,
                y=self.spectroscopy_pulse_aom_amplitude.get(),
            )

        # Start on profile 0 with AOM off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        t_pi_pulse = self.spectroscopy_pulse_time.get()

        # Ensure we're on profile 0
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=0)
        delay(t_pi_pulse / 2)
        # Phase step & turn off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=1)

        delay(self.delay_between_interferometry_pulses.get())

        # PI PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=1)
        delay(t_pi_pulse)
        # Phase step and turn off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=2)

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=2)
        delay(t_pi_pulse / 2)
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)


class UpBeamInterferometrySUServo(
    TripleImageRedMOTFastKineticsMixin,
):
    """
    Up beam interferometry - delivery phase shift
    """

    def build_fragment(self):
        super().build_fragment()

        # Include the checkpoint fragment defined above
        self.setattr_fragment("up_beam_interferometry", _UpBeamInterferometryFrag)
        self.up_beam_interferometry: _UpBeamInterferometryFrag

        # Expose important params
        self.setattr_param_rebind("phase_step", self.up_beam_interferometry)
        self.setattr_param_rebind(
            "delay_between_interferometry_pulses", self.up_beam_interferometry
        )
        self.setattr_param_rebind(
            "spectroscopy_pulse_aom_amplitude", self.up_beam_interferometry
        )
        self.setattr_param_rebind(
            "spectroscopy_pulse_aom_detuning", self.up_beam_interferometry
        )
        self.setattr_param_rebind(
            "spectroscopy_pulse_time", self.up_beam_interferometry
        )

    # Override the experiment hook
    @kernel
    def do_experiment_after_red_mot_hook(self):
        return self.up_beam_interferometry.do_experiment_after_red_mot_hook()

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.phase_step,
                    "y": self.excitation_fraction,
                },
                constants={
                    "t_dead": -100.0,
                },
            )
        ]


UpBeamInterferometrySUServoExp = make_fragment_scan_exp(UpBeamInterferometrySUServo)
