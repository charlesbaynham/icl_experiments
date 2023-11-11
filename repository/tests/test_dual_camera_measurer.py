import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import BGCorrectedMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_3d_mot import Red3DMOTFrag

logger = logging.getLogger(__name__)


class TestDualCameraMeasurerHardwareTrigger(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "camera_bg_corrected", BGCorrectedMeasurement, hardware_trigger=True
        )
        self.camera_bg_corrected: BGCorrectedMeasurement

    @kernel
    def run_once(self):
        self.core.break_realtime()

        delay(20e-3)

        self.camera_bg_corrected.trigger_background()

        delay(20e-3)
        self.camera_bg_corrected.trigger_signal()

        # Wait for all RTIO events to complete
        self.core.break_realtime()
        self.core.wait_until_mu(now_mu())

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.camera_bg_corrected.save_data()


TestDualCameraMeasurerHardwareTrigger = make_fragment_scan_exp(
    TestDualCameraMeasurerHardwareTrigger
)
