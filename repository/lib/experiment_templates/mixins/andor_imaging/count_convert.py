from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from sipyco.packed_exceptions import GenericRemoteException

from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin


class CountConvertWithEMGainMixin(EMGainMixin):
    """
    Adds EM gain control to the Andor camera and converts the EM counts to photons

    This mixin will default to turning the gain off unless the user checks a
    box. DO NOT ADD THIS MIXIN TO AN EXPERIMENT UNLESS YOU ARE CERTAIN YOU KNOW
    WHAT YOU ARE DOING!!! If not, you might break a camera that cost >£30k.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "count_convert_mode",
            BoolParam,
            description="Enable count convert mode",
            default=False,
        )
        self.count_convert_mode: BoolParamHandle

        self.setter.func_to_call = self._set_gain_and_count_convert

    def host_setup(self):
        super().host_setup()
        self.andor_camera_control.cam.set_count_convert_wavelength(461.0)

    @kernel
    def _set_gain_and_count_convert(self):
        self._set_gain_if_changed()
        if self.count_convert_mode.get():
            self._set_count_convert()

    @rpc
    def _set_count_convert(self):
        try:
            self.andor_camera_control.cam.set_count_convert_mode(2)
        except GenericRemoteException as e:
            if "DRV_ACQUIRING" in e.args[0]:
                self.andor_camera_control.cam.stop_acquisition()
                self.andor_camera_control.cam.set_count_convert_mode(2)
                self.andor_camera_control.cam.start_acquisition()
            else:
                raise e

    def host_cleanup(self):
        if hasattr(self, "cam"):
            self.andor_camera_control.cam.set_count_convert_mode(0)
        super().host_cleanup()


CountConvertWithEMGain = CountConvertWithEMGainMixin
