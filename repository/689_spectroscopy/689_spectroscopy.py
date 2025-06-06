import logging

from artiq.language import delay
from artiq.language import kernel
from artiq.language import parallel
from artiq.language import sequential
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.field_boost import FieldBoostMixin
from repository.lib.experiment_templates.mixins.optical_pumping import (
    DroppedPumpedLatticeMixin,
)
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class SpectroscopyWithKinetics_UpBeam(
    FieldBoostMixin,
    TripleImageRedMOTFastKineticsMixin,
    SpectroscopyParamsMixin,
    ConstantBeamsMixin,
    RedMOTWithExperiment,
):
    """
    689nm spectroscopy UP

    689nm spectroscopy with fast kinetics imaging using the red up beam
    """

    def build_fragment(self):
        # We assume that the up beam has already been configured by the MOT
        # sequence, but that we must control the amplitude
        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

        super().build_fragment()

        # Rebind the default fast kinetics X ROIs and set their defaults
        self.setattr_param_like(
            "roi_x0",
            self.andor_camera_control,
            "roi_0_x0",
            description="Grabber ROI x0",
            default=constants.ANDOR_689_FAST_KINETICS_X0,
        )
        self.setattr_param_like(
            "roi_x1",
            self.andor_camera_control,
            "roi_0_x1",
            description="Grabber ROI x1",
            default=constants.ANDOR_689_FAST_KINETICS_X1,
        )

        self.roi_x0: FloatParamHandle
        self.roi_x1: FloatParamHandle

        for c in "012":
            self.andor_camera_control.bind_param(f"roi_{c}_x0", self.roi_x0)
            self.andor_camera_control.bind_param(f"roi_{c}_x1", self.roi_x1)

        # Set up some defaults
        self.setattr_param_rebind(
            "fluorescence_pulse_duration",
            self.fluorescence_pulse,
            "fluorescence_pulse_duration",
            default=constants.FLUORESCENCE_PULSE_DURATION_689,
        )

    def get_default_analyses(self):
        return [
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.excitation_fraction,
                },
                constants={
                    "t_dead": 0,
                },
            )
        ]

    @kernel
    def pre_expansion_hook(self):
        # Disable servoing, turn off the switch, configure the amplitude and
        # open the shutter in preparation for a quick pulse
        with parallel:
            self.red_mot.red_beam_controller.set_mot_detuning(
                self.spectroscopy_pulse_aom_detuning.get()
            )
            with sequential:
                self.up_beam_suservo.set_channel_state(
                    rf_switch_state=False, enable_iir=False
                )
                self.up_beam_suservo.suservo_channel.set_y(
                    profile=self.up_beam_suservo.suservo_profile,
                    y=self.spectroscopy_pulse_aom_amplitude.get(),
                )

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


class SpectroscopySingleImage_UpBeam(
    FieldBoostMixin,
    TripleImageRedMOTFastKineticsMixin,
    DroppedPumpedLatticeMixin,
    SpectroscopyParamsMixin,
    ConstantBeamsMixin,
    RedMOTWithExperiment,
):
    """
    689nm spectroscopy UP - single image

    689nm spectroscopy using the red up beam
    """

    def build_fragment(self):
        # We assume that the up beam has already been configured by the MOT
        # sequence, but that we must control the amplitude
        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

        super().build_fragment()

    @kernel
    def pre_expansion_hook(self):
        # Disable servoing, turn off the switch, configure the amplitude and
        # open the shutter in preparation for a quick pulse
        with parallel:
            self.red_mot.red_beam_controller.set_mot_detuning(
                self.spectroscopy_pulse_aom_detuning.get()
            )
            with sequential:
                self.up_beam_suservo.set_channel_state(
                    rf_switch_state=False, enable_iir=False
                )
                self.up_beam_suservo.suservo_channel.set_y(
                    profile=self.up_beam_suservo.suservo_profile,
                    y=self.spectroscopy_pulse_aom_amplitude.get(),
                )

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_lattice()
        self.post_sequence_cleanup_hook_andor()


# SpectroscopyWithKineticsMOTExp = make_fragment_scan_exp(
#     SpectroscopyWithKinetics_MOTBeam
# )
SpectroscopyWithKineticyUpExp = make_fragment_scan_exp(SpectroscopyWithKinetics_UpBeam)
SpectroscopySingleImageUpBeam = make_fragment_scan_exp(SpectroscopySingleImage_UpBeam)
