import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.pumped_lattice import (
    DroppedPumpedLatticeMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.spectroscopy_params import (
    SpectroscopyParamsMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageMOTMixin,
)


logger = logging.getLogger(__name__)

CLOCK_BEAM_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_up"]


class ClockSpecFromLatticeFrag(
    SpectroscopyParamsMixin,
    DroppedPumpedLatticeMixin,
    TripleImageMOTMixin,
    RedMOTWithExperiment,
):
    """
    Clock spectroscopy from dropped lattice

    Load into a lattice, pump into a stretched state, drop the atoms by ramping
    the lattice, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    def pre_build_fragment_hook(self):
        self.setattr_fragment(
            "clock_up",
            LibSetSUServoStatic,
            "suservo_aom_698_up_switch",
        )
        self.clock_up: LibSetSUServoStatic

    @kernel
    def before_start_hook(self):
        self.core.break_realtime()
        self.clock_up.set_suservo(
            freq=CLOCK_BEAM_INFO.frequency + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=self.spectroscopy_pulse_aom_amplitude.get(),
            attenuation=CLOCK_BEAM_INFO.attenuation,
            rf_switch_state=False,
            enable_iir=False,
        )

    @kernel
    def do_spectroscopy_hook(self):
        self.clock_up.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.clock_up.set_channel_state(rf_switch_state=False, enable_iir=False)

    @kernel
    def do_first_pulse(self, andor_exposure):
        self._do_pulse(andor_exposure)
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()


ClockSpecFromLattice = make_fragment_scan_exp(ClockSpecFromLatticeFrag)
