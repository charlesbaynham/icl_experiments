import logging

from artiq.coredevice.core import Core
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.ramping_phase import GeneralRampingPhase

logger = logging.getLogger(__name__)


class GeneralRampingPhaseNoGeneral(GeneralRampingPhase):
    duration_default = 50e-3

    suservos = [
        "suservo_aom_singlepass_461_imaging_delivery",
        "suservo_aom_singlepass_461_pushbeam",
        "suservo_aom_singlepass_461_2dmot_b",
        "suservo_aom_singlepass_689_red_mot_diagonal",
    ]
    default_suservo_nominal_setpoints = [1.0, 2.0, 0.01, 5.5]
    default_suservo_setpoint_multiples_start = [1.0, 2.5, 100, 0.0]
    default_suservo_setpoint_multiples_end = [0.0, 2.5, 1, 1.0]

    urukuls = [
        "urukul9910_aom_doublepass_689_red_injection",
        "urukul9910_aom_doublepass_461_injection",
    ]
    default_urukul_nominal_frequencies = [340e6, 200e6]
    default_urukul_detunings_start = [1e6, 0.0]
    default_urukul_detunings_end = [-1e6, 0.0]
    default_urukul_amplitudes_start = [1.0] * 2
    default_urukul_amplitudes_end = [1.0] * 2


class DaisyChainedPhasesBase(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "test_phase_a",
            GeneralRampingPhaseNoGeneral,
        )
        self.test_phase_a: GeneralRampingPhaseNoGeneral

        self.setattr_fragment(
            "test_phase_b",
            GeneralRampingPhaseNoGeneral,
        )
        self.test_phase_b: GeneralRampingPhaseNoGeneral

        self.setattr_fragment(
            "test_phase_c",
            GeneralRampingPhaseNoGeneral,
        )
        self.test_phase_c: GeneralRampingPhaseNoGeneral

        self.configure_daisy_chaining()

    def configure_daisy_chaining(self):
        pass

    @kernel
    def run_once(self):
        logger.info("Precomputing handles")
        self.test_phase_a.precalculate_dma_handle()
        self.test_phase_b.precalculate_dma_handle()
        self.test_phase_c.precalculate_dma_handle()

        logger.info("Starting test phases")

        self.core.break_realtime()

        self.test_phase_a.do_phase()
        self.test_phase_b.do_phase()
        self.test_phase_c.do_phase()

        logger.info("Phase queuing completed")

        logger.info(
            "now_mu = %d, get_rtio_counter_mu = %d, diff=%fs",
            now_mu(),
            self.core.get_rtio_counter_mu(),
            self.core.mu_to_seconds(now_mu() - self.core.get_rtio_counter_mu()),
        )

        self.core.wait_until_mu(now_mu())

        logger.info("Phase output completed")


class DaisyChainedPhasesSpecific(DaisyChainedPhasesBase):
    def configure_daisy_chaining(self):
        self.test_phase_b.daisy_chain_with_previous_phase(
            self.test_phase_a,
            suservos=[
                "suservo_aom_singlepass_461_imaging_delivery",
                "suservo_aom_singlepass_461_2dmot_b",
            ],
        )
        self.test_phase_c.daisy_chain_with_previous_phase(
            self.test_phase_b,
            suservos=[
                "suservo_aom_singlepass_461_imaging_delivery",
                "suservo_aom_singlepass_461_2dmot_b",
            ],
        )


# TODO: Solve transitivity error chaining nominal c->b->a
class DaisyChainedPhasesAll(DaisyChainedPhasesBase):
    def configure_daisy_chaining(self):
        self.test_phase_b.daisy_chain_with_previous_phase(
            self.test_phase_a,
            suservos="all",
        )
        self.test_phase_c.daisy_chain_with_previous_phase(
            self.test_phase_b,
            suservos="all",
        )


DaisyChainedPhasesSpecificExp = make_fragment_scan_exp(DaisyChainedPhasesSpecific)
DaisyChainedPhasesAllExp = make_fragment_scan_exp(DaisyChainedPhasesAll)
