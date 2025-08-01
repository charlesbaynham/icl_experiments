import logging

from artiq.coredevice.core import Core
from artiq.coredevice.fastino import Fastino
from artiq.language.core import host_only
from artiq.language.core import kernel
from ndscan.experiment import ExpFragment

# from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

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

        self.channel = channel

        self.setattr_param(
            "freq_step",
            FloatParam,
            description="Toptica Frequency Step",
            default=0.0,
            unit="MHz",
        )
        self.freq_step: FloatParamHandle

        # self.setattr_param(
        #     "target_voltage",
        #     FloatParam,
        #     description="Target Voltage",
        #     unit="V",
        #     default=0.0,
        # )
        # self.target_voltage: FloatParamHandle

        # self.setattr_param(
        #     "arc_factor",
        #     FloatParam,
        #     description="ARC Factor",
        #     default=0.02,
        #     unit="V/V",
        #     scale=1,
        # )
        # self.arc_factor: FloatParamHandle

        self.arc_factor = 0.04
        self.voltage_min = -10.0  # we have a 1/5 attenuator so we can go all the way
        self.voltage_max = 10.0
        self.voltage: float = 0.0

    @host_only
    def host_setup(self):
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "voltage_min",
            "voltage_max",
            "channel",
        }
        self.first_run = True
        super().host_setup()

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()
        self.core.break_realtime()
        if self.first_run:
            self.fastino0.init()
            self.first_run = False

        self.voltage = self.frequency_to_voltage(self.freq_step.get())

        self.core.break_realtime()
        self.reset_freq()

    @kernel
    def device_cleanup(self):
        self.device_cleanup_subfragments()
        self.core.break_realtime()
        self.reset_freq()

    @kernel
    def frequency_to_voltage(self, freq: float) -> float:
        voltage = freq / (TOPTICA_461_ANALOG_SCALE)
        if not self.check_voltage_lim(voltage):
            raise ValueError("Voltage out of range")
        return voltage

    @kernel
    def check_voltage_lim(self, voltage: float) -> bool:
        return self.voltage_min <= voltage <= self.voltage_max

    @kernel
    def step_freq(self):
        self.fastino0.set_dac(self.channel, self.voltage)

    @kernel
    def reset_freq(self):
        self.fastino0.set_dac(self.channel, 0.0)
