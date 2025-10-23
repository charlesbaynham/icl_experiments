from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib.constants import URUKULED_BEAMS
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)


class MessWithIJDsFrag(ExpFragment):
    """
    Mess with the IJDs
    """

    def build_fragment(self):
        self.setattr_fragment(
            "blue_doublepass_toggler",
            make_toggle_list_of_beams(
                urukul_beam_infos=[URUKULED_BEAMS["blue_doublepass_injection"]]
            ),
        )
        self.blue_doublepass_toggler: ToggleListOfBeams

        self.setattr_fragment(
            "blue_singlepass_toggler",
            make_toggle_list_of_beams(
                urukul_beam_infos=[URUKULED_BEAMS["blue_singlepass_injection"]]
            ),
        )
        self.blue_singlepass_toggler: ToggleListOfBeams

        self.setattr_fragment(
            "blue_doublepass_default_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[URUKULED_BEAMS["blue_doublepass_injection"]],
                use_automatic_setup=True,
                use_automatic_turnon=True,
            ),
        )
        self.blue_doublepass_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "blue_singlepass_default_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[URUKULED_BEAMS["blue_singlepass_injection"]],
                use_automatic_setup=True,
                use_automatic_turnon=True,
            ),
        )
        self.blue_singlepass_default_setter: SetBeamsToDefaults

    @kernel
    def run_once(self) -> None:
        # Turn off IJD1's AOM
        self.blue_doublepass_toggler.turn_off_beams()
        delay(1.0)
        self.blue_doublepass_toggler.turn_on_beams()
        delay(10.0)

        # Mess with IJD2 and IJD3
        self.blue_singlepass_toggler.turn_off_beams()
        delay(1.0)
        self.blue_singlepass_toggler.turn_on_beams()
        delay(10.0)


MessWithIJDs = make_fragment_scan_exp(MessWithIJDsFrag)
