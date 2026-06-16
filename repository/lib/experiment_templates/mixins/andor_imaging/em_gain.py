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

EM_GAIN_DISABLE_DATASET = "DISABLE_EM_GAIN"


class EMGainMixin(AndorImagingBase):
    """
    Adds EM gain control to the Andor camera

    This mixin defaults to turning the gain ON, but it is always gated by the
    safety interlock dataset (see :data:`EM_GAIN_DISABLE_DATASET`): if that
    dataset forbids EM gain, the gain stays off regardless of the parameter.
    DO NOT ADD THIS MIXIN TO AN EXPERIMENT UNLESS YOU ARE CERTAIN YOU KNOW
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
            default=True,
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

        # Initialize or read the EM gain safety interlock dataset
        disable_em_gain = self.get_dataset(EM_GAIN_DISABLE_DATASET, default=True)
        self.set_dataset(
            EM_GAIN_DISABLE_DATASET,
            disable_em_gain,
            broadcast=True,
            persist=True,
            archive=False,
        )
        self.disable_em_gain = disable_em_gain

        # Safety interlock: if the dataset forbids EM gain it always wins, so EM
        # gain is kept OFF even though the parameter defaults to (and may be set
        # to) True. See _em_gain_active() for where this is enforced.
        if disable_em_gain:
            if self.em_gain_enabled.get():
                logger.warning(
                    "EM gain is enabled in parameters but the safety interlock "
                    "dataset '%s' is set to True. EM gain will be kept DISABLED. "
                    "To use EM gain, set the dataset '%s' to False using the "
                    "ARTIQ dashboard dataset manager, then restart the "
                    "experiment.\nSomeone set this up for a reason - don't "
                    "ignore it!",
                    EM_GAIN_DISABLE_DATASET,
                    EM_GAIN_DISABLE_DATASET,
                )
            else:
                logger.info(
                    "EM gain safety interlock is ENABLED (dataset '%s' = True). "
                    "EM gain cannot be activated unless this dataset is set to "
                    "False.",
                    EM_GAIN_DISABLE_DATASET,
                )

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

    @host_only
    def _em_gain_active(self) -> bool:
        """Whether EM gain should actually be applied.

        EM gain is only active when the parameter requests it *and* the safety
        interlock dataset does not forbid it. The interlock always wins.
        """
        return self.em_gain_enabled.get() and not self.disable_em_gain

    @rpc
    def _set_camera_em_gain(self):
        if self._em_gain_active():
            logger.warning("Setting EMCCD gain to %f. BEWARE!!!", self.em_gain.get())
            self._set_gain_guarded(self.em_gain.get())
        else:
            logger.warning("EM gain is disabled - not setting")
            self._set_gain_guarded(0)

    def host_cleanup(self):
        self._set_gain_guarded(0)
        if self._em_gain_active():
            logger.info("EM gain turned off again")
        return super().host_cleanup()
