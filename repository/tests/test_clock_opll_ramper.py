from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import now_mu
from ndscan.experiment import *
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController


class TestClockRamper(ExpFragment):

    def build_fragment(self):

        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("clock_opll", ClockOPLLController)
        self.clock_opll: ClockOPLLController

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

    @kernel
    def run_once(self):

        start_time = now_mu()

        self.clock_opll.clock_frequency_ramper.start_ramp(1e6, 80e6, 82e6, 1)

        delay(1.0)

        self.clock_opll.clock_frequency_ramper.stop_ramp()

        end_time = now_mu()

        new_freq = 80e6 + 1e6 * self.core.mu_to_seconds(end_time - start_time + 1)

        self.clock_opll.clock_OPLL_offset.set(new_freq)

        delay(1.0)

        self.clock_opll.clock_frequency_ramper.start_ramp(1e6, 80e6, new_freq, 2)

        delay(1.0)
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        self.clock_opll.clock_OPLL_offset.set(80e6)
        delay(1.0)


class TestLaunchFromXODTFrag(
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    DipoleTrapWithExperiment,
):
    """
    Test launching from an XODT

    Load into an XODT, then use the up clock beam for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()


TestClockRamperExp = make_fragment_scan_exp(TestClockRamper)
TestLaunchFromXODTFExp = make_fragment_scan_exp(TestLaunchFromXODTFrag)
