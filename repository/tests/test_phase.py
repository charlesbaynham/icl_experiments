"""
Test a simple phase
"""
import logging

from artiq.coredevice.core import Core
from artiq.experiment import *
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import TFloat
from ndscan.experiment import *

from repository.lib import constants
from repository.lib.fragments.beams.beam_setters import make_set_beams_to_default
from repository.lib.fragments.beams.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.ramping_phase import GeneralRampingPhase

logger = logging.getLogger(__name__)


class TestPhase(GeneralRampingPhase):
    suservos = [
        "suservo_aom_singlepass_689_red_mot_diagonal",
    ]

    default_suservo_nominal_setpoints = [1.0]
    default_suservo_setpoint_multiples_start = [1.0]
    default_suservo_setpoint_multiples_end = [0.1]

    duration_default = 100e-3
    time_step_default = 10e-3


class ExpFragWithPhaseFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "test_phase",
            TestPhase,
        )
        self.test_phase: GeneralRampingPhase

        self.setattr_fragment(
            "diagonal_beam_setter",
            make_set_beams_to_default([constants.AOM_BEAMS["red_mot_diagonal"]]),
        )
        self.diagonal_beam_setter: SetBeamsToDefaults

        self.setattr_param(
            "delay_between_phases",
            FloatParam,
            description="Delay before starting DMA playback",
            default=600e-6,
            unit="us",
            min=0.0,
        )

        self.setattr_param(
            "num_repeats",
            IntParam,
            description="Number of times to repeat phase",
            default=10,
            min=1,
        )

    @kernel
    def run_once(self):
        logger.info("Precomputing handle")
        self.test_phase.precalculate_dma_handle()

        logger.info("Enabling diagonal beam")
        self.core.break_realtime()
        self.diagonal_beam_setter.turn_on_all()

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


ExpFragWithPhase = make_fragment_scan_exp(ExpFragWithPhaseFrag)
