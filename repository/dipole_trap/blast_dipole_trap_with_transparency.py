import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODT,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)

logger = logging.getLogger(__name__)


class BlastSingleDipoleWithTransparencyFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
):
    """
    Blast a single XODT with 689 while protecting it with the transparency beam
    """

    def build_fragment(self):
        self.setattr_param(
            "blast_duration",
            FloatParam,
            "Duration of the red MOT sigma+ blast",
            default=10e-3,
            unit="ms",
        )
        self.blast_duration: FloatParamHandle

        self.setattr_fragment(
            "transparency_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["blue_transparency_beam"]
                ],
                use_automatic_setup=True,
                use_automatic_turnon=False,
            ),
        )
        self.transparency_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "transparency_toggler",
            make_toggle_list_of_beams(
                beam_infos=[constants.SUSERVOED_BEAMS["blue_transparency_beam"]]
            ),
        )
        self.transparency_toggler: ToggleListOfBeams

        self.setattr_fragment(
            "red_mot_sigmaplus_toggler",
            make_toggle_list_of_beams(
                beam_infos=[constants.SUSERVOED_BEAMS["red_mot_sigmaplus"]]
            ),
        )
        self.red_mot_sigmaplus_toggler: ToggleListOfBeams

        super().build_fragment()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Turn on the transparency beam to protect the atoms in the dipole trap
        self.transparency_toggler.turn_on_beams()

        # Blast the atoms with the red MOT sigma+ beam
        self.red_mot_sigmaplus_toggler.turn_on_beams()
        delay(self.blast_duration.get())
        self.red_mot_sigmaplus_toggler.turn_off_beams()

        # Turn off the transparency beam
        self.transparency_toggler.turn_off_beams()


BlastSingleDipoleWithTransparency = make_fragment_scan_exp(
    BlastSingleDipoleWithTransparencyFrag
)
