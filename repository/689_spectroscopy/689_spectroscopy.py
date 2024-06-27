import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)
from repository.lib.fragments.red_mot.red_mot_mixins.field_boost import FieldBoostMixin
from repository.lib.fragments.red_mot.red_mot_mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)

logger = logging.getLogger(__name__)


class SpectroscopyWithKinetics_MOTBeam(
    FieldBoostMixin, TripleImageFastKineticsMixin, SpectroscopyParamsMixin
):
    """
    689nm spectroscopy MOTBEAM

    689nm spectroscopy with fast kinetics imaging using the red MOT beam
    """

    def pre_build_fragment_hook(self):
        self.setattr_fragment(
            "red_axial_minus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_689_red_mot_sigmaminus",
        )
        self.red_axial_minus: LibSetSUServoStatic

    @kernel
    def pre_expansion_hook(self):
        self.red_mot.red_beam_controller.set_mot_detuning(
            self.spectroscopy_pulse_aom_detuning.get()
        )

        self.red_axial_minus.suservo_channel.set_y(
            profile=self.red_axial_minus.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

    @kernel
    def do_spectroscopy_hook(self):
        self.red_axial_minus.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.red_axial_minus.set_channel_state(rf_switch_state=False, enable_iir=False)


class SpectroscopyWithKinetics_UpBeam(
    FieldBoostMixin,
    TripleImageFastKineticsMixin,
    SpectroscopyParamsMixin,
    RedMOTWithExperiment,
):
    """
    689nm spectroscopy UP

    689nm spectroscopy with fast kinetics imaging using the red up beam
    """

    def pre_build_fragment_hook(self):
        # We assume that the up beam has already been configured by the MOT
        # sequence, but that we must control the amplitude
        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

    @kernel
    def pre_expansion_hook(self):
        # Disable servoing, turn off the switch, configure the amplitude and
        # open the shutter in preparation for a quick pulse
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)
        self.up_beam_suservo.suservo_channel.set_y(
            profile=self.up_beam_suservo.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

    @kernel
    def do_spectroscopy_hook(self):
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


SpectroscopyWithKineticsMOTExp = make_fragment_scan_exp(
    SpectroscopyWithKinetics_MOTBeam
)
SpectroscopyWithKineticyUpExp = make_fragment_scan_exp(SpectroscopyWithKinetics_UpBeam)
