import logging
from enum import Enum
from enum import unique

from artiq.language import delay
from artiq.language import kernel
from artiq.language import parallel
from artiq.language import sequential
from ndscan.experiment import *
from ndscan.experiment.parameters import EnumParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import ParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.field_boost import FieldBoostMixin
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


@unique
class SpectroscopyBeam(Enum):
    sigmaminus = "red_mot_sigmaminus"
    sigmaplus = "red_mot_sigmaplus"
    up = "red_up"


class _RedSpectroscopyBase(
    SpectroscopyParamsMixin,
    ExponentialDecayMixin,
    FieldBoostMixin,
    RedMOTWithExperiment,
):
    """
    Sets up the 689 beam for spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.suservo_setters: dict[str, LibSetSUServoStatic] = {}

        for beam_enum in SpectroscopyBeam:
            f = self.setattr_fragment(
                f"{beam_enum.value}_suservo",
                LibSetSUServoStatic,
                constants.SUSERVOED_BEAMS[beam_enum.value].suservo_device,
            )
            self.suservo_setters[beam_enum] = f

        self.setattr_param(
            "spectroscopy_beam",
            EnumParam,
            default=SpectroscopyBeam.up,
            description="Spectroscopy beam",
        )
        self.spectroscopy_beam: ParamHandle

        self.setattr_param_rebind(
            "fluorescence_pulse_duration",
            self.fluorescence_pulse,
            "fluorescence_pulse_duration",
            default=constants.FLUORESCENCE_PULSE_DURATION_689,
        )

    def host_setup(self):
        super().host_setup()

        self.spectroscopy_beam_suservo = self.suservo_setters[
            self.spectroscopy_beam.get()
        ]

    @kernel
    def prepare_red_beam(self):
        # Disable servoing, turn off the switch, configure the amplitude and
        # open the shutter in preparation for a quick pulse
        with parallel:
            self.red_mot.red_beam_controller.set_mot_detuning(
                self.spectroscopy_pulse_aom_detuning.get()
            )
            with sequential:
                self.spectroscopy_beam_suservo.set_channel_state(
                    rf_switch_state=False, enable_iir=False
                )
                self.spectroscopy_beam_suservo.suservo_channel.set_y(
                    profile=self.spectroscopy_beam_suservo.suservo_profile,
                    y=self.spectroscopy_pulse_aom_amplitude.get(),
                )

    @kernel
    def do_red_spectroscopy(self):
        self.spectroscopy_beam_suservo.set_channel_state(
            rf_switch_state=True, enable_iir=False
        )
        delay(self.spectroscopy_pulse_time.get())
        self.spectroscopy_beam_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )


class RedSpectroscopyDipoleTrap(
    _RedSpectroscopyBase, FieldBoostMixin, DipoleTrapWithExperiment
):
    """
    Sets up the 689 beam for spectroscopy in a dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~post_dipole_trap_hook`
    * :meth:`~set_postnarrowband_fields_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "bias_field_settling_time",
            FloatParam,
            default=20e-3,
            unit="ms",
            description="Bias field settling time before experiment",
        )
        self.bias_field_settling_time: FloatParamHandle

    @kernel
    def set_postnarrowband_fields_hook(self):
        # Prevent the FieldBoost field setting
        self.set_fields_default()

    @kernel
    def post_dipole_trap_hook(self):
        # Set fields pre-experiment
        self.field_boost()

        self.prepare_red_beam()

        delay(self.bias_field_settling_time.get())

        # Turn off the trap
        self.post_dipole_trap_hook_default()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_red_spectroscopy()
