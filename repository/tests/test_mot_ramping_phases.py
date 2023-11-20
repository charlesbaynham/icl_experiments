import logging

from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_beam_controller import RedBeamController
from repository.measure_red_mot import RampingRedPhase


logger = logging.getLogger(__name__)


class TestPhase(RampingRedPhase):
    duration_default = 50e-3
    start_detuning_default = 150e3
    end_detuning_default = 50e3
    start_gradient_default = 5.0
    end_gradient_default = 1.0
    start_suservo_nominal_multiple_default = 100.0
    end_suservo_nominal_multiple_default = 10.0


class TestRampingPhaseFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("red_mot_controller", RedBeamController)
        self.red_mot_controller: RedBeamController

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        self.setattr_fragment(
            "test_phase",
            TestPhase,
            red_mot_controller=self.red_mot_controller,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.test_phase: TestPhase

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

        self.core.reset()

        for _ in range(self.num_repeats.get()):
            delay(self.delay_between_phases.get())
            self.test_phase.do_phase()

        logger.info("Phase queuing completed")

        self.core.wait_until_mu(now_mu())

        logger.info("Phase output completed")


TestRampingPhase = make_fragment_scan_exp(TestRampingPhaseFrag)
