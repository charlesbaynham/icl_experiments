import logging
from typing import *

from artiq.coredevice.core import Core
from artiq.experiment import *
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

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
        "urukul9910_aom_doublepass_461_master_to_ijd1",
    ]
    default_urukul_nominal_frequencies = [340e6, 200e6]
    default_urukul_detunings_start = [1e6, 0.0]
    default_urukul_detunings_end = [-1e6, 0.0]
    default_urukul_amplitudes_start = [1.0] * 2
    default_urukul_amplitudes_end = [1.0] * 2


class GeneralRampingPhaseWithGeneral(GeneralRampingPhaseNoGeneral):
    @kernel
    def general_setter(self, things: TList(TFloat)):
        if len(things) != 3:
            raise RuntimeError("There must be three things")

        for i in range(3):
            print(things[i])

    general_setter_default_starts = [0.0, 1.0, 999]
    general_setter_default_ends = [1.0, -10, 999]
    general_setter_names = ["thing_a", "thing_b", "thing_c"]
    general_setter_param_options = [{}, {}, {"min": -1000, "max": 1000}]


class GeneralRampingPhaseNoSUServo(GeneralRampingPhase):
    duration_default = 50e-3

    urukuls = [
        "urukul9910_aom_doublepass_689_red_injection",
        "urukul9910_aom_doublepass_461_master_to_ijd1",
    ]
    default_urukul_nominal_frequencies = [340e6, 200e6]
    default_urukul_detunings_start = [1e6, 0.0]
    default_urukul_detunings_end = [-1e6, 0.0]
    default_urukul_amplitudes_start = [1.0] * 2
    default_urukul_amplitudes_end = [1.0] * 2


class GeneralRampingPhaseNoAD9910(GeneralRampingPhase):
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


def make_test_expfrag(test_phase: Type):
    class ExpFragWithPhase(ExpFragment):
        def build_fragment(self):
            self.setattr_device("core")
            self.core: Core

            self.setattr_fragment(
                "test_phase",
                test_phase,
            )
            self.test_phase: GeneralRampingPhase

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

    return ExpFragWithPhase


def test_GeneralRampingPhaseWithGeneral(fragment_precompiler):
    fragment_precompiler(make_test_expfrag(GeneralRampingPhaseWithGeneral))


def test_GeneralRampingPhaseNoGeneral(fragment_precompiler):
    fragment_precompiler(make_test_expfrag(GeneralRampingPhaseNoGeneral))


def test_GeneralRampingPhaseNoSUServo(fragment_precompiler):
    fragment_precompiler(make_test_expfrag(GeneralRampingPhaseNoSUServo))


def test_GeneralRampingPhaseNoAD9910(fragment_precompiler):
    fragment_precompiler(make_test_expfrag(GeneralRampingPhaseNoAD9910))


### Try daisy-chaining phases


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

        self.configure_daisy_chaining()

    @kernel
    def run_once(self):
        logger.info("Precomputing handles")
        self.test_phase_a.precalculate_dma_handle()
        self.test_phase_b.precalculate_dma_handle()

        logger.info("Starting test phases")

        self.core.break_realtime()

        self.test_phase_a.do_phase()
        self.test_phase_b.do_phase()

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


def test_daisychained_phases_specific(fragment_precompiler):
    built_frag = fragment_precompiler(DaisyChainedPhasesSpecific)

    free_params = list(built_frag.test_phase_b._free_params.keys())

    assert not any(
        [("setpoint_nominal" in free_param_name) for free_param_name in free_params]
    )

    assert not any(
        [
            ("setpoint_multiple_start_" in free_param_name)
            and ("suservo_aom_singlepass_461_imaging_delivery" in free_param_name)
            for free_param_name in free_params
        ]
    )
    assert (
        sum(
            [
                ("setpoint_multiple_start_" in free_param_name)
                and ("suservo_aom_singlepass_461_pushbeam" in free_param_name)
                for free_param_name in free_params
            ]
        )
        == 1
    )
    assert not any(
        [
            ("setpoint_multiple_start_" in free_param_name)
            and ("suservo_aom_singlepass_461_2dmot_b" in free_param_name)
            for free_param_name in free_params
        ]
    )
    assert (
        sum(
            [
                ("setpoint_multiple_start_" in free_param_name)
                and ("suservo_aom_singlepass_689_red_mot_diagonal" in free_param_name)
                for free_param_name in free_params
            ]
        )
        == 1
    )

    assert "setpoint_global_multiple_start" in free_params


class DaisyChainedPhasesAll(DaisyChainedPhasesBase):
    def configure_daisy_chaining(self):
        self.test_phase_b.daisy_chain_with_previous_phase(
            self.test_phase_a, suservos="all"
        )


def test_daisychained_phases_all(fragment_precompiler):
    built_frag = fragment_precompiler(DaisyChainedPhasesAll)

    free_params = list(built_frag.test_phase_b._free_params.keys())

    assert not any(
        [("setpoint_nominal" in free_param_name) for free_param_name in free_params]
    )

    assert not any(
        [
            ("setpoint_multiple_start_" in free_param_name)
            for free_param_name in free_params
        ]
    )

    assert "setpoint_global_multiple_start" not in free_params
