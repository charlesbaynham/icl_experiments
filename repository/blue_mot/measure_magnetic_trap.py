import logging

from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.dual_camera_measurer import BGCorrectedMeasurement

logger = logging.getLogger(__name__)


class MeasureMagneticTrapWithCameraFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        self.setattr_fragment(
            "camera_interface", BGCorrectedMeasurement, hardware_trigger=True
        )
        self.camera_interface: BGCorrectedMeasurement

        self.setattr_param_rebind("sr87", self.mot_controller)

        self.setattr_param_rebind(
            "mot_loading_time",
            self.mot_controller,
            "loading_time",
            description="Time to wait for the 3D MOT to load",
        )
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "dark_time",
            FloatParam,
            description="Time to wait in the dark for the magnetic trap",
            default=0,
            min=0,
            unit="ms",
            step=1,
        )
        self.dark_time: FloatParamHandle

        self.setattr_param(
            "mot_recapture_time",
            FloatParam,
            description="Time to wait after repumping before imaging",
            default=10e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.mot_recapture_time: FloatParamHandle

        # Ensure that both cameras are on for the same length of time as the blue
        # fluorescence is pulsed
        self.setattr_param_rebind(
            "exposure",
            self.camera_interface,
            "exposure_horiz",
            default=1e-3,
            description="Camera exposure and fluorescence pulse length",
        )
        self.camera_interface.bind_param(
            "exposure_vert",
            self.exposure,
        )
        self.exposure: FloatParamHandle

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "exponential_decay",
                data={
                    "x": self.dark_time,
                    "y": self.camera_interface.image_vertical_mean,
                },
            )
        ]

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(20e-3)

        # Repump atoms from the previous sequence
        self.mot_controller.turn_on_repumpers()

        delay(
            100e-3
        )  # Wait to allow atoms to disperse if there were any hanging around

        # Load MOT without repumpers
        self.mot_controller.load_magnetic_trap(repump_at_end=False)

        if self.dark_time.get() > 0:
            # Turn off the push and MOT beams
            self.mot_controller.turn_off_3d_and_2d_beams()

            # Wait for some time while the atoms sit in their magnetic trap
            delay(self.dark_time.get())

            # Turn on the MOT beams and the repumpers (but not the push beam)
            self.mot_controller.turn_on_3d_beams()
        else:
            self.mot_controller.turn_off_push_beam()
        delay(20e-9)
        self.mot_controller.turn_on_repumpers()
        delay(self.mot_recapture_time.get())

        # Take a photo
        self.camera_interface.trigger_signal()

        # Clear out the atoms
        delay(100e-3)
        self.mot_controller.turn_off_3d_beams(
            ignore_shutters=True
        )  # but leave repumps on
        delay(50e-3)
        self.mot_controller.turn_on_3d_beams(ignore_shutters=True)
        delay(10e-3)
        self.camera_interface.trigger_background()

        # Trigger the host to retrieve the data
        self.core.wait_until_mu(now_mu() + 1e-3)
        self.camera_interface.save_data()


MeasureMagneticTrapWithCamera = make_fragment_scan_exp(
    MeasureMagneticTrapWithCameraFrag
)
