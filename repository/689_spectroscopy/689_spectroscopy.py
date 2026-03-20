import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.field_boost import FieldBoostMixin
from repository.lib.experiment_templates.mixins.spectroscopy_params import (
    add_spectroscopy_params,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.red_mot import RedMOTThreePhaseFrag

logger = logging.getLogger(__name__)


class _Spectroscopy689Mixin(RedMOTWithExperiment):
    """
    Mixin for spectroscopy with the 689 up beam
    """

    def build_fragment(self):
        super().build_fragment()

        # Implement all spectroscopy in a checkpoint frag:
        class Spectroscopy689(RedMOTCheckpoints):
            def build_fragment(
                self,
                red_mot: RedMOTThreePhaseFrag,
            ):
                add_spectroscopy_params(self)

                self.setattr_device("core")
                self.core: Core

                self.red_mot = red_mot
                self.kernel_invariants.add("red_mot")

                # We assume that the up beam has already been configured by the MOT
                # sequence, but that we must control the amplitude
                self.setattr_fragment(
                    "up_beam_suservo",
                    LibSetSUServoStatic,
                    constants.SUSERVOED_BEAMS["red_up"].suservo_device,
                )
                self.up_beam_suservo: LibSetSUServoStatic

            @kernel
            def pre_expansion_checkpoint(self):
                self.pre_expansion_checkpoint_subfragments()

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
            def do_689_spectroscopy(self):
                self.up_beam_suservo.set_channel_state(
                    rf_switch_state=True, enable_iir=False
                )
                delay(self.spectroscopy_pulse_time.get())
                self.up_beam_suservo.set_channel_state(
                    rf_switch_state=False, enable_iir=False
                )

        self.setattr_fragment("spectroscopy_689", Spectroscopy689, red_mot=self.red_mot)
        self.spectroscopy_689: Spectroscopy689

        # Expose important params
        self.setattr_param_rebind("spectroscopy_pulse_time", self.spectroscopy_689)
        self.setattr_param_rebind(
            "spectroscopy_pulse_aom_amplitude", self.spectroscopy_689
        )
        self.setattr_param_rebind(
            "spectroscopy_pulse_aom_detuning", self.spectroscopy_689
        )

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
    def do_experiment_after_red_mot_hook(self):
        """
        Do the 689nm spectroscopy pulse
        """
        self.spectroscopy_689.do_689_spectroscopy()


class SpectroscopyWithKinetics_UpBeam(
    FieldBoostMixin,
    TripleImageRedMOTFastKineticsMixin,
    ConstantBeamsMixin,
    _Spectroscopy689Mixin,
    RedMOTWithExperiment,
):
    """
    689nm spectroscopy UP - fast kinetics

    Mixin for 689nm spectroscopy with fast kinetics imaging using the red up
    beam.

    Also leaves the lattice / dipole traps beams on constant, so these will be
    enabled if the lasers are have been (manually) turned on before running this
    experiment.
    """


class SpectroscopySingleImage_UpBeam(
    FieldBoostMixin,
    SingleAndorImage,
    ConstantBeamsMixin,
    _Spectroscopy689Mixin,
    RedMOTWithExperiment,
):
    """
    689nm spectroscopy UP - single image

    Mixin for 689nm spectroscopy with a single image using the red up
    beam.

    Also leaves the lattice / dipole traps beams on constant, so these will be
    enabled if the lasers are have been (manually) turned on before running this
    experiment.
    """


SpectroscopyWithKineticyUpExp = make_fragment_scan_exp(SpectroscopyWithKinetics_UpBeam)
SpectroscopySingleImageUpBeam = make_fragment_scan_exp(SpectroscopySingleImage_UpBeam)
