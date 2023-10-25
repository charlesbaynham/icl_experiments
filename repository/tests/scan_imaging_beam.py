from artiq.coredevice.core import Core
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
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.suservo import LibSetSUServoStatic


class ImageBlueMOT(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.suservo_setter: LibSetSUServoStatic = self.setattr_fragment(
            "suservo_setter",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_imaging_switch",
        )

        self.setattr_param(
            "expansion_time",
            FloatParam,
            "Expansion time of blue MOT",
            default=10e-3,
            unit="ms",
        )
        self.expansion_time: FloatParamHandle

        self.setattr_param(
            "image_time",
            FloatParam,
            "Expansion time of blue MOT",
            default=200e-6,
            unit="us",
        )
        self.image_time: FloatParamHandle

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()

        self.blue_mot.init()
        self.blue_mot.load_mot(clearout=False)

        delay(1.0)

        self.blue_mot.turn_off_3d_and_2d_beams()

        delay(self.expansion_time.get())

        with parallel:
            with sequential:
                self.suservo_setter.set_channel_state(
                    rf_switch_state=True, enable_iir=False
                )
                delay(self.image_time.get())
                self.suservo_setter.set_channel_state(
                    rf_switch_state=False, enable_iir=False
                )

            self.dual_cameras.trigger()

        self.core.wait_until_mu(now_mu())

        self.dual_cameras.save_data()


ImageBlueMOTExp = make_fragment_scan_exp(ImageBlueMOT)
