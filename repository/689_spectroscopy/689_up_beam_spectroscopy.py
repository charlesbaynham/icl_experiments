import logging

from artiq.language import delay
from artiq.language import kernel
from artiq.language import parallel
from artiq.language import sequential
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics_base import (
    TripleFKConfig,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.field_boost import FieldBoostMixin
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)

logger = logging.getLogger(__name__)


class SpectroscopyWithKineticsUpBeamFrag(
    FieldBoostMixin,
    TripleImageRedMOTFastKineticsMixin,
    EMGainMixin,
    SpectroscopyParamsMixin,
    ConstantBeamsMixin,
    RedMOTWithExperimentBase,
):
    """
    689nm spectroscopy UP

    689nm spectroscopy with fast kinetics imaging using the red up beam.

    Pulses the red up beam after the red MOT and images via fast kinetics. The
    spectroscopy AOM detuning, applied compensation-coil boosts (FieldBoostMixin)
    and pulse time/amplitude are the scan axes for Zeeman spectroscopy.

    EMGainMixin is included so the EM gain is forced to 0 during imaging (it
    defaults disabled and only reads the ``DISABLE_EM_GAIN`` safety interlock).
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

        # Set up some defaults
        self.setattr_param_rebind(
            "fluorescence_pulse_duration",
            self.fluorescence_pulse,
            "fluorescence_pulse_duration",
            default=constants.FLUORESCENCE_PULSE_DURATION_689,
        )

    def get_andor_camera_config_hook(self):
        # Use the narrow 689-specific X ROI for the up beam (the ROI config was
        # rewritten since this experiment was archived: ROI coordinates now live
        # on the andor_camera_config fragment rather than as roi_<n>_x* params on
        # andor_camera_control). Keep the generic Y extent.
        f = self.setattr_fragment(
            "andor_camera_config",
            TripleFKConfig,
            x0=constants.ANDOR_689_FAST_KINETICS_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_689_FAST_KINETICS_X1,
            y1=constants.ANDOR_ROI_Y1,
        )
        self.andor_camera_config: TripleFKConfig
        return f

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


SpectroscopyWithKineticsUpBeam = make_fragment_scan_exp(
    SpectroscopyWithKineticsUpBeamFrag
)
