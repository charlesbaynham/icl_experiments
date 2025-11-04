import logging

import sipyco
import sipyco.packed_exceptions
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import rpc
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
            max=100,
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
        self.setter: Setter

    def host_setup(self):
        super().host_setup()
        self.previous_em_gain = -1.0

    @kernel
    def _set_gain_if_changed(self):
        new_gain = self.em_gain.get()
        if new_gain != self.previous_em_gain:
            self._set_camera_em_gain()
            self.previous_em_gain = new_gain

    @host_only
    def _set_gain_guarded(self, gain):
        """
        Set EM gain, stopping and restarting the acquisition if necessary
        """
        if not hasattr(self.andor_camera_control, "cam"):
            logger.info("Camera not controlled by ARTIQ - not setting EM gain")
            return

        try:
            self.andor_camera_control.cam.set_EMCCD_gain(gain)
        except sipyco.packed_exceptions.GenericRemoteException as e:
            if "DRV_ACQUIRING" in e.args[0]:
                # The camera was acquiring already. Stop, set and restart
                self.andor_camera_control.cam.stop_acquisition()
                self.andor_camera_control.cam.set_EMCCD_gain(gain)
                self.andor_camera_control.cam.start_acquisition()
            else:
                # Different error
                raise e

    @rpc
    def _set_camera_em_gain(self):
        if self.em_gain_enabled.get():
            logger.warning("Setting EMCCD gain to %f. BEWARE!!!", self.em_gain.get())
            self._set_gain_guarded(self.em_gain.get())
        else:
            logger.warning("EM gain is disabled - not setting")
            self._set_gain_guarded(0)

    def host_cleanup(self):
        self._set_gain_guarded(0)
        if self.em_gain_enabled.get():
            logger.info("EM gain turned off again")
        return super().host_cleanup()
