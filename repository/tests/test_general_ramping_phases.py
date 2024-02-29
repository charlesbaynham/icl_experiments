import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib.fragments.ramping_phase_alt import GeneralRampingPhase


logger = logging.getLogger(__name__)


class TestGeneralRampingPhase(GeneralRampingPhase):
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


class TestGeneralRampingPhaseFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "test_phase",
            TestGeneralRampingPhase,
        )
        self.test_phase: TestGeneralRampingPhase

        self.setattr_param(
            "delay_between_phases",
            FloatParam,
            description="Delay before starting DMA playback",
            default=600e-6,
            unit="us",
            min=0.0,
        )
        self.delay_between_phases: FloatParamHandle

        self.setattr_param(
            "num_repeats",
            IntParam,
            description="Number of times to repeat phase",
            default=10,
            min=1,
        )
        self.num_repeats: IntParamHandle

    @kernel
    def run_once(self):
        logger.info("Precomputing handle")
        self.test_phase.precalculate_dma_handle()

        logger.info("Starting test phase")

        self.core.break_realtime()

        for _ in range(self.num_repeats.get()):
            delay(self.delay_between_phases.get())
            self.test_phase.do_phase()

        logger.info("Phase queuing completed")

        logger.info(
            "now_mu = %d, get_rtio_counter_mu = %d, diff=%fs",
            now_mu(),
            self.core.get_rtio_counter_mu(),
            self.core.mu_to_seconds(now_mu() - self.core.get_rtio_counter_mu()),
        )

        self.core.wait_until_mu(now_mu())

        logger.info("Phase output completed")


TestGeneralRampingPhaseExp = make_fragment_scan_exp(TestGeneralRampingPhaseFrag)
