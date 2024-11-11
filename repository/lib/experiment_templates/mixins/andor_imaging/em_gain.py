import logging

from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)

logger = logging.getLogger(__name__)


class EMGain(AndorImagingBase):
    """
    Adds EM gain control to the Andor camera

    This mixin will default to turning the gain off unless the user checks a
    box. DO NOT ADD THIS MIXIN TO AN EXPERIMENT UNLESS YOU ARE CERTAIN YOU KNOW
    WHAT YOU ARE DOING!!! If not, you might break a camera that cost >£30k.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    None.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "em_gain_enabled",
            BoolParam,
            description="Enable EM gain. Might blow up the camera",
            default=False,
        )
        self.em_gain_enabled: BoolParamHandle

        self.setattr_param(
            "em_gain",
            FloatParam,
            description="EM gain level. Ignored if not enabled",
            default=30,
            min=0,
            max=30,
        )
        self.em_gain: FloatParamHandle

        # Define a "Setter" fragment which just calls "_set_camera_em_gain" every device_setup
        class Setter(Fragment):
            def build_fragment(self, func_to_call):
                self.func_to_call = func_to_call

            @kernel
            def device_setup(self):
                self.func_to_call()

        self.setattr_fragment("setter", Setter, func_to_call=self._set_gain_if_changed)

    def host_setup(self):
        super().host_setup()
        self.previous_em_gain = -1.0

    @kernel
    def _set_gain_if_changed(self):
        new_gain = self.em_gain.get()
        if new_gain != self.previous_em_gain:
            self._set_camera_em_gain()
            self.previous_em_gain = new_gain

    @rpc
    def _set_camera_em_gain(self):
        if self.em_gain_enabled.get():
            logger.warning("Setting EMCCD gain to %f. BEWARE!!!", self.em_gain.get())
            self.andor_camera_control.cam.set_EMCCD_gain(self.em_gain.get())
        else:
            logger.warning("EM gain is disabled - not setting")
            self.andor_camera_control.cam.set_EMCCD_gain(0)

    def host_cleanup(self):
        logger.warning("EM gain turned off again")
        self.andor_camera_control.cam.set_EMCCD_gain(0)
        return super().host_cleanup()
