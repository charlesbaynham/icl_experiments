import logging

from artiq.coredevice.core import Core
from artiq.coredevice.fastino import Fastino
from artiq.language.core import kernel, host_only, rpc
from ndscan.experiment import ExpFragment
from wand.server import ControlInterface as WANDControlInterface
from artiq.language.core import delay, now_mu, at_mu

# from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
import time

from repository.lib.constants import TOPTICA_461_ANALOG_SCALE

logger = logging.getLogger(__name__)


class SetTopticaAnalogFrag(ExpFragment):
    """
    Use the fastino to offset the topica frequency
    It needs to be told what arc frequency you're currently using
    and it relies on the empirically measured
    scale factor in constants.

    If we want to use this with other lasers, it can be extended
    to take the laser as a parameter and use the appropriate scale factor
    from a list.

    channel is the fastino channel to use
    """

    def build_fragment(self, channel: int = 0):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("fastino0")
        self.fastino0: Fastino

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.channel = channel

        self.setattr_param(
            "freq_step",
            FloatParam,
            description="Toptica Frequency Step",
            default=0.0,
            unit="MHz",
        )
        self.freq_step: FloatParamHandle

        self.setattr_param(
            "arc_factor",
            FloatParam,
            description="ARC Factor",
            default=0.02,
            unit="V/V",
            scale=1,
        )
        self.arc_factor: FloatParamHandle

        self.voltage_min = -10.0  # we have a 1/5 attenuator so we can go all the way
        self.voltage_max = 10.0

        self.setattr_result("frequency_461", FloatChannel)
        self.frequency_461: FloatChannel
        self.setattr_result("frequency_diff", FloatChannel)
        self.frequency_diff: FloatChannel

        self.setattr_param("read_wait", FloatParam, "Settling time", default=100e-3, unit="ms")
        self.read_wait: FloatParamHandle

    @host_only
    def host_setup(self):
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "voltage_min",
            "voltage_max",
            "channel",
        }
        super().host_setup()

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()
        self.core.break_realtime()
        self.fastino0.init()

    @kernel
    def convert_freq(self, freq: float) -> float:
        voltage = freq / (TOPTICA_461_ANALOG_SCALE * self.arc_factor.get())
        if not self.check_voltage_lim(voltage):
            raise ValueError("Voltage out of range")
        return voltage

    @kernel
    def check_voltage_lim(self, voltage: float) -> bool:
        return self.voltage_min <= voltage <= self.voltage_max

    @kernel
    def step_freq(self, freq: float):
        self.fastino0.set_dac(self.channel, self.convert_freq(freq))

    @rpc
    def get_frequency(self) -> float:
        time.sleep(self.read_wait.get())
        _, freq_461, _ = self.wand_server.get_freq("461")
        return float(freq_461)

    @rpc
    def push_frequency(self, freq: float):
        self.frequency_461.push(freq)

    @kernel
    def run_once(self):
        f1 = self.get_frequency()
        delay(100e-3)
        # now = now_mu()
        self.step_freq(self.freq_step.get())
        # delay(self.read_wait.get())
        f2 = self.get_frequency()
        logger.info("Set frequency %f MHz", self.freq_step.get() / 1e6)
        self.frequency_461.push(f2*1e-12)
        self.frequency_diff.push((f2 - f1)*1e-6)
