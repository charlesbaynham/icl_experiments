from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import make_fragment_scan_exp
from ndscan.params import ParamHandle as FloatParamHandle
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
        self.setattr_param(
            "ijd1_off_delay",
            FloatParam,
            description="Duration to keep IJD1 beam off",
            default=1.0,
            unit="s",
            min=0.0,
            max=100.0,
        )
        self.ijd1_off_delay: FloatParamHandle

        self.setattr_param(
            "ijd1_on_delay",
            FloatParam,
            description="Duration to keep IJD1 beam on",
            default=10.0,
            unit="s",
            min=0.0,
            max=100.0,
        )
        self.ijd1_on_delay: FloatParamHandle

        self.setattr_param(
            "ijd23_off_delay",
            FloatParam,
            description="Duration to keep IJD2/3 beams off",
            default=1.0,
            unit="s",
            min=0.0,
            max=100.0,
        )
        self.ijd23_off_delay: FloatParamHandle

        self.setattr_param(
            "ijd23_on_delay",
            FloatParam,
            description="Duration to keep IJD2/3 beams on",
            default=10.0,
            unit="s",
            min=0.0,
            max=100.0,
        )
        self.ijd23_on_delay: FloatParamHandle

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
        delay(self.ijd1_off_delay.get())
        self.blue_doublepass_toggler.turn_on_beams()
        delay(self.ijd1_on_delay.get())

        # Mess with IJD2 and IJD3
        self.blue_singlepass_toggler.turn_off_beams()
        delay(self.ijd23_off_delay.get())
        self.blue_singlepass_toggler.turn_on_beams()
        delay(self.ijd23_on_delay.get())


MessWithIJDs = make_fragment_scan_exp(MessWithIJDsFrag)
