import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import parallel
from ndscan.experiment import *
from artiq.experiment import sequential
from pyaion.fragments.suservo import LibSetSUServoStatic
from ndscan.experiment.parameters import BoolParamHandle
from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class _RedSpectroscopyBase(SpectroscopyParamsMixin, RedMOTWithExperiment):
    """
    Sets up the 689 beam for spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "down_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["down_689"].suservo_device,
        )
        self.down_beam_suservo: LibSetSUServoStatic

        self.setattr_param(
            "use_up_beam",
            BoolParam,
            default=True,
            description="True = up, False = down",
        )
        self.use_up_beam: BoolParamHandle

    def host_setup(self):
        super().host_setup()

        if self.use_up_beam.get():
            self.spectroscopy_beam_suservo = self.up_beam_suservo
        else:
            self.spectroscopy_beam_suservo = self.down_beam_suservo

    @kernel
    def post_narrowband_hook_red_spectroscopy(self):
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
    def post_narrowband_hook(self):
        self.post_narrowband_hook_default()
        self.post_narrowband_hook_red_spectroscopy()

    @kernel
    def do_red_spectroscopy(self):
        self.spectroscopy_beam_suservo.set_channel_state(
            rf_switch_state=True, enable_iir=False
        )
        delay(self.spectroscopy_pulse_time.get())
        self.spectroscopy_beam_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )


class RedSpectroscopyDipoleTrap(_RedSpectroscopyBase, DipoleTrapWithExperiment):
    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_red_spectroscopy()
