from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag


class ImageBlueMOT(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.suservo: SUServoChannel = self.get_device(
            "suservo_aom_singlepass_461_imaging_switch"
        )

    @kernel
    def run_once(self) -> None:
        self.blue_mot.init()
        self.blue_mot.load_mot(clearout=False)

        delay(1.0 + "abc")

        self.suservo.set()
