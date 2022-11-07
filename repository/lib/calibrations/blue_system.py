import logging

from artiq.coredevice.suservo import Channel
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.experiment import RTIOUnderflow
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

from repository.lib.constants import BLUE_INJECTION_AOM_ATTENUATION
from repository.lib.constants import BLUE_INJECTION_AOM_DEFAULT_FREQUENCY
from repository.lib.fragments.suservo import LibSetSUServoStatic

logger = logging.getLogger(__name__)


class BlueInjectionAOM(Calibration):
    """
    Ensure that the double-pass AOM which injects the blue diodes has been set
    up and turned on
    """

    def build_calibration(self):
        self.setup_completed = False

        self.setattr_param(
            "frequency",
            FloatParam,
            description="Frequency of the double-pass injection AOM",
            default=BLUE_INJECTION_AOM_DEFAULT_FREQUENCY,
            min=0,
            max=400e6,  # from AD9910 specs
            unit="MHz",
            step=0.1,
        )
        self.setattr_param(
            "attenuation",
            FloatParam,
            description="Attenuation on Urukul's variable attenuator",
            default=BLUE_INJECTION_AOM_ATTENUATION,
            min=0,
            max=31.5,
        )

        # self.setattr_fragment("LibSetSUServoStatic", LibSetSUServoStatic)
        # self.LibSetSUServoStatic: LibSetSUServoStatic

        # self.setattr_device("core")
        # self.suservo_injection_aom: Channel = self.get_device("suservo_injection_aom")

    # @kernel
    # def device_setup(self) -> None:
    #     self.device_setup_subfragments()

    #     try:
    #         self.suservo_injection_aom.servo.init()
    #     except RTIOUnderflow:
    #         self.core.break_realtime()
    #         self.suservo_injection_aom.servo.init()

    def run_once(self):
        if self.setup_completed:
            self.status.push(CalibrationResult.OK)
        else:
            self.status.push(CalibrationResult.BAD_EXPIRED)

        self.data.push(None)

    # @kernel
    # def fix_own_state(self):
    #     self.setup_completed = True

    # self.LibSetSUServoStatic.set_suservo(
    # self.frequency.get(), 1.0, self.attenuation.get()
    # )


TurnOnBlueInjectionAOM = make_fragment_scan_exp(BlueInjectionAOM)
