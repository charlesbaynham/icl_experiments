from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from matplotlib.pylab import int64
from ndscan.experiment import *
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForLMTMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)
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
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
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
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class TestLMTInterferometryFrag(
    LMTInterferometryMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperiment,
):
    """
    Test LMT interferometry without launch

    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()

    @kernel
    def calculate_frequency_for_first_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = (
            self.core.mu_to_seconds(
                t_pulse_start_mu - self.t_velocity_slicing_pulse_centre_mu
            )
            + t_pi_pulse / 2
        )
        return -self._calculate_chirp_required(t_drop) + self.momentum_kick.get() + 9e3

    @kernel
    def calculate_frequency_for_first_lmt_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )

        return (
            +self._calculate_chirp_required(t_drop)
            - 2 * self.momentum_kick.get()
            + self.first_lmt_freq.get()
        )

    @kernel
    def calculate_frequency_for_second_lmt_pulse(
        self, t_pulse_start_mu: int64
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )

        return -self._calculate_chirp_required(t_drop) + 3 * self.momentum_kick.get()

    @kernel
    def _calculate_chirp_required(self, t_drop: float):
        return t_drop * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK


TestLMTInterferometryExp = make_fragment_scan_exp(
    TestLMTInterferometryFrag, max_rtio_underflow_retries=0
)
TestClockRamperExp = make_fragment_scan_exp(TestClockRamper)
TestLaunchFromXODTFExp = make_fragment_scan_exp(
    TestLaunchFromXODTFrag, max_rtio_underflow_retries=0
)
