import logging

from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import TBool
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.result_channels import FloatChannel

from repository.lib import constants

logger = logging.getLogger(__name__)


class AndorCameraControl(Fragment):
    """
    Control the Andor camera and associated shutters / triggers

    For now, just open the shutter and trigger - readout and setup is done manually on the Windows lab PC.
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("grabber0")
        self.grabber: Grabber = self.grabber0

        self.ttl_trigger: TTLOut = self.get_device("ttl_camera_trigger_andor")
        self.ttl_shutter: TTLOut = self.get_device("ttl_shutter_andor")

        self.setattr_result("andor_roi_sum", FloatChannel)
        self.andor_roi_sum: FloatChannel

        self.setattr_result(
            "andor_roi_mean", FloatChannel, display_hints={"priority": -1}
        )
        self.andor_roi_mean: FloatChannel

        # %% Params

        self.setattr_param(
            "shutter_delay",
            FloatParam,
            "Time to allow for shutter to open before imaging",
            default=constants.ANDOR_CAMERA_SHUTTER_OPEN_TIME,
            unit="ms",
            min=0.0,
        )
        self.shutter_delay: FloatParamHandle

        self.setattr_param(
            "roi_x0",
            IntParam,
            "Grabber ROI x0",
            default=constants.ANDOR_ROI_X0,
            min=0,
            max=512,
        )
        self.setattr_param_like(
            "roi_x1",
            self,
            "roi_x0",
            default=constants.ANDOR_ROI_X1,
            description="Grabber ROI x1",
        )
        self.setattr_param_like(
            "roi_y0",
            self,
            "roi_x0",
            default=constants.ANDOR_ROI_Y0,
            description="Grabber ROI y0",
        )
        self.setattr_param_like(
            "roi_y1",
            self,
            "roi_x0",
            default=constants.ANDOR_ROI_Y1,
            description="Grabber ROI y1",
        )

        self.roi_x0: FloatParamHandle
        self.roi_x1: FloatParamHandle
        self.roi_y0: FloatParamHandle
        self.roi_y1: FloatParamHandle

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "ttl_trigger",
            "ttl_shutter",
        }

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        self.ttl_shutter.off()
        delay(self.core.coarse_ref_period)
        self.ttl_trigger.off()
        delay(self.core.coarse_ref_period)
        self.ttl_shutter.output()
        delay(self.core.coarse_ref_period)
        self.ttl_trigger.output()

        # Setup one grabber ROI
        self.grabber.setup_roi(
            0,
            self.roi_x0.get(),
            self.roi_y0.get(),
            self.roi_x1.get(),
            self.roi_y1.get(),
        )

    @kernel
    def device_cleanup(self) -> None:
        self.device_cleanup_subfragments()

        # Ensure the camera's protective shutter is closed
        self.core.break_realtime()
        self.ttl_shutter.off()

    @kernel
    def set_shutter(self, state: TBool):
        """
        Open or close the protective shutter

        This will be automatically closed at the end of a sequence if you
        forget, but you should close it immediately after use to avoid damaging
        the camera with lots of light while it's in EM gain mode.
        """
        self.ttl_shutter.set_o(state)

    @kernel
    def trigger(self, exposure: TFloat, control_shutter=False):
        """
        Trigger an aquisition

        For now, you must manually set up the camera to respond to external triggers.

        You should call :meth:`~.save_data` to read out the configured ROI at the end of your sequence.

        If control_shutter == True, open the shutter <shutter_delay> in advance and then close if afterwards.

        TODO: Finish Andor fragment to fully control camera, including readout
        """

        # Turn grabber ROI 0 on
        self.grabber.gate_roi(0x01)

        if control_shutter:
            shutter_delay_mu = self.core.seconds_to_mu(self.shutter_delay.get())
            delay_mu(-shutter_delay_mu)
            self.ttl_shutter.on()
            delay_mu(shutter_delay_mu)

        self.ttl_trigger.pulse(exposure)

        if control_shutter:
            self.ttl_shutter.off()

    @kernel
    def save_data(self, timeout_mu):
        """
        Save data retrieved by Grabber

        Must be run at the end of the sequence. Will block until timeout_mu if no data
        was taken, i.e. if the camera was set up incorrectly

        Will consume all slack and break_realtime.
        """
        # Get data
        data = [0]
        self.grabber.input_mu(data, timeout_mu=timeout_mu)

        # Disable the ROI again
        self.core.break_realtime()
        self.grabber.gate_roi(0x00)

        self.andor_roi_sum.push(data[0])
        area = (self.roi_x1.get() - self.roi_x0.get()) * (
            self.roi_y1.get() - self.roi_y0.get()
        )
        if area == 0:
            self.andor_roi_mean.push(0)
        else:
            self.andor_roi_mean.push(data[0] / area)
