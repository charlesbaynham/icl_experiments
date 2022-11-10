import logging

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import portable
from artiq.experiment import RTIOUnderflow
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
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
        self.setattr_device("core")
        self.core: Core

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
        self.frequency: FloatParamHandle
        self.attenuation: FloatParamHandle

        self.setattr_fragment(
            "LibSetSUServoStatic",
            LibSetSUServoStatic,
            "suservo_aom_doublepass_461_injection",
        )
        self.LibSetSUServoStatic: LibSetSUServoStatic

    @kernel
    def run_once(self):
        # This calibration is always OK - its turns on the AOM in the setup
        # which is always called directly before this run_once method
        self.status.push(CalibrationResult.OK)

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()

        self.LibSetSUServoStatic.set_suservo(
            self.frequency.get(), 1.0, self.attenuation.get()
        )


TurnOnBlueInjectionAOM = make_fragment_scan_exp(BlueInjectionAOM)
