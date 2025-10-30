import logging

from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.ad9910_ramper import AD9910Ramper
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_beam_controller import RED_SUSERVO_INFOS
from repository.lib.fragments.red_mot.red_beam_controller import RedBeamController

logger = logging.getLogger(__name__)


class ShelveInBlueMOTMixin(RedMOTWithExperiment):
    """
    Add shelving during blue MOT to protect cold atoms from loss mechanisms
    """

    def build_fragment(self):
        super().build_fragment()

        class ShelvingFrag(Fragment):
            def build_fragment(
                self,
                red_beam_controller: RedBeamController,
            ):
                self.setattr_device("core")
                self.core: Core

                self.red_beam_controller = red_beam_controller

                self.injection_aom_static_frequency = (
                    red_beam_controller.injection_aom_static_frequency
                )

                # Fast ramping of the AD9910 controlling the injection AOM
                self.setattr_fragment(
                    "injection_aom_ramper",
                    AD9910Ramper,
                    "urukul9910_aom_doublepass_689_red_injection",
                )
                self.injection_aom_ramper: AD9910Ramper

                self.setattr_param(
                    "ramp_frequency",
                    FloatParam,
                    "689 injection AOM ramp frequency during blue MOT",
                    unit="kHz",
                    default=constants.RED_INJECTION_AOM_RAMP_FREQUENCY,
                )
                self.ramp_frequency: FloatParamHandle

                self.setattr_param(
                    "ramp_lower_detuning",
                    FloatParam,
                    "Lower detuning for 689 injection AOM ramp during blue MOT",
                    unit="MHz",
                    default=0.0,
                )
                self.ramp_lower_detuning: FloatParamHandle

                self.setattr_param(
                    "ramp_upper_detuning",
                    FloatParam,
                    "Upper detuning for 689 injection AOM ramp during blue MOT",
                    unit="MHz",
                    default=3.0e6,
                )
                self.ramp_upper_detuning: FloatParamHandle

                self.setattr_param(
                    "global_setpoint_multiple",
                    FloatParam,
                    "Multiplier for red beam setpoints during blue MOT shelving",
                    default=1.0,
                )
                self.global_setpoint_multiple: FloatParamHandle

                # SUServo setters for red MOT beams

                self.suservo_setters: list[LibSetSUServoStatic] = []
                self.suservo_default_setpoints: list[float] = []
                for beam in RED_SUSERVO_INFOS:
                    f = self.setattr_fragment(
                        beam.name, LibSetSUServoStatic, beam.suservo_device
                    )

                    self.suservo_setters.append(f)  # type: ignore
                    self.suservo_default_setpoints.append(beam.setpoint)

                self.ramp_rate = 0.0

            @kernel
            def device_setup(self) -> None:
                self.device_setup_subfragments()

                # Precalculate the ramp rate required to get the requested modulation frequency
                self.ramp_rate = abs(
                    (self.ramp_lower_detuning.get() - self.ramp_upper_detuning.get())
                    * self.ramp_frequency.get()
                )

            @kernel
            def before_blue_mot_hook(self):
                self.red_beam_controller.turn_on_mot_beams()

                for ind_beam in range(len(self.suservo_setters)):
                    self.suservo_setters[ind_beam].set_setpoint(
                        self.global_setpoint_multiple.get()
                        * self.suservo_default_setpoints[ind_beam]
                    )

                self.injection_aom_ramper.start_ramp(
                    self.ramp_rate,
                    self.injection_aom_static_frequency.get()
                    + self.ramp_lower_detuning.get(),
                    self.injection_aom_static_frequency.get()
                    + self.ramp_upper_detuning.get(),
                    2,  # negative saw
                )

        self.setattr_fragment(
            "shelving_frag",
            ShelvingFrag,
            red_beam_controller=self.red_mot.red_beam_controller,
        )
        self.shelving_frag: ShelvingFrag

    @kernel
    def before_blue_mot_hook(self):
        delay(constants.SRS_SHUTTER_DELAY + 1e-3)
        self.shelving_frag.before_blue_mot_hook()
