import logging

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.suservo import SUServo
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.master.worker_db import DummyDevice
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import IntParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.read_adc import ReadSUServoADC
from repository.lib.fragments.suservo import LibSetSUServoStatic

logger = logging.getLogger(__name__)


class DisplaySUServoMonitorsFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "waittime",
            FloatParam,
            description="Time between measurements",
            default=0.1,
            min=0,
            max=1000,
            unit="s",
            step=0.01,
        )
        self.waittime: FloatParamHandle

        beam_info_names = list(constants.AOM_BEAMS.keys())
        self.setattr_argument(
            "beam_info_name",
            EnumerationValue(
                beam_info_names,
                default=beam_info_names[0],
            ),
        )
        self.beam_info_name: str

        self.setattr_argument(
            "turn_on_beam_with_default_settings",
            BooleanValue(True),
        )
        self.turn_on_beam_with_default_settings: bool

        self.setattr_argument(
            "disable_servoing",
            BooleanValue(True),
        )
        self.disable_servoing: bool

        # %% devices

        self.beam_info = constants.AOM_BEAMS[self.beam_info_name or beam_info_names[0]]

        if self.disable_servoing:
            self.beam_info.servo_enabled = False

        self.suservo_channel_device: SUServoChannel = self.get_device(
            self.beam_info.suservo_device
        )

        if isinstance(self.suservo_channel_device, DummyDevice):
            # In building - use placeholder values
            self.suservo: SUServo = DummyDevice()
            self.sampler_channel_number = 0
        else:
            self.suservo = self.suservo_channel_device.servo
            # This is a convention in the AION lab:
            self.sampler_channel_number = self.suservo_channel_device.servo_channel

        # Define result channels as outputs
        self.setattr_result("voltage")
        self.voltage: ResultChannel

        # Get beam setter fragment
        self.setattr_fragment(
            "beam_default_setter",
            SetBeamsToDefaults,
            default_beam_infos=[self.beam_info],
        )
        self.beam_default_setter: SetBeamsToDefaults

        # Get SUServo reader fragment
        self.setattr_fragment(
            "adc_reader", ReadSUServoADC, self.suservo, self.sampler_channel_number
        )
        self.adc_reader: ReadSUServoADC

        # FIXME: Hack to get suservo control too
        self.setattr_fragment(
            "suservo_controller",
            LibSetSUServoStatic,
            channel=self.beam_info.suservo_device,
        )
        self.suservo_controller: LibSetSUServoStatic

        self.setattr_param(
            "pgia_gain",
            IntParam,
            description="PGA gain",
            default=1,
        )
        self.pgia_gain: IntParamHandle

        # %% Kernel params

        self.first_run = True

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        if self.first_run:
            self.core.break_realtime()
            delay(10 * ms)
            if self.turn_on_beam_with_default_settings:
                self.beam_default_setter.turn_on_all(shutter_state=True)

            # FIXME
            self.suservo_controller.set_pgia_gain_mu(self.pgia_gain.get())

            self.first_run = False

    @kernel
    def run_once(self):
        delay(self.waittime.get())

        v = self.adc_reader.read_adc()

        self.voltage.push(v)


DisplaySUServoMonitors = make_fragment_scan_exp(DisplaySUServoMonitorsFrag)
