import logging
import time

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.experiment import rpc
from artiq.experiment import RTIOUnderflow
from artiq.experiment import TFloat
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.lib.utils import get_local_devices

from repository.lib import constants
from repository.lib.fragments.read_suservo_adc import ReadSUServoADC

logger = logging.getLogger(__name__)
SAMPLING_WAIT_TIME = 0.001  # wait 1ms between points


class ScanKoheronCurrentFrag(ExpFragment):
    """
    Set a Koheron CTL200 laser driver's current and measure an analog input in response
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "current",
            FloatParam,
            description="Current to set",
            default=0,
            min=0,
            max=400,
            unit="mA",
            step=0.1,
        )
        self.current: FloatParamHandle

        self.setattr_param(
            "temperature",
            FloatParam,
            description="Temperature",
            default=constants.IJD1_TEMPERATURE,
            min=8000,
            max=15000,
            unit="Ohms",
            scale=1,
            step=0.1,
        )
        self.temperature: FloatParamHandle

        self.setattr_param(
            "temperature_waittime",
            FloatParam,
            description="Time to wait after a temperature change",
            default=30,
            min=0,
            max=1000,
            unit="s",
            step=1,
        )
        self.temperature_waittime: FloatParamHandle

        self.setattr_param(
            "num_points",
            IntParam,
            description="Number of voltage points to take, spaced by 1ms",
            default=10,
            min=1,
            max=1000,
        )
        self.num_points: IntParamHandle

        self.setattr_argument("always_wait_at_start", BooleanValue(default=False))
        self.always_wait_at_start: bool

        # Choose the controller to set:
        controller_names = [
            k
            for k, v in self.get_device_db().items()
            if (
                ("type" in v and v["type"] == "controller")
                and (
                    "command" in v
                    and "aqctl_koheron_ctl200_laser_driver" in v["command"]
                )
            )
        ]
        if not controller_names:
            raise ValueError("No CTL200 Koheron controllers found in device_db")
        self.setattr_argument("controller_name", EnumerationValue(controller_names))
        self.controller: CTL200 = self.get_device(self.controller_name)

        # And the suservo channel to read
        suservos = get_local_devices(self, SUServo)
        if not suservos:
            raise ValueError("No suservo devices found in device_db")
        self.setattr_argument("suservo_device", EnumerationValue(suservos))
        self.setattr_argument(
            "suservo_channel",
            NumberValue(
                default=0, ndecimals=0, scale=1, step=1, min=0, max=7, type="int"
            ),
        )
        self.suservo_channel: int
        self.suservo_device: str

        self.print_debug_statements = logger.isEnabledFor(logging.DEBUG)

        # # Load the sampler utility from pyaion
        # self.setattr_fragment("sampler_reader", SamplerReader)
        # self.sampler_reader: SamplerReader

        self.setattr_fragment(
            "suservo_reader", ReadSUServoADC, self.suservo_device, self.suservo_channel
        )
        self.suservo_reader: ReadSUServoADC

        # And define a results channel as output
        self.setattr_result("voltage")
        self.voltage: ResultChannel

        self.is_first_cycle = True

    def host_setup(self):
        if not self.controller.status():
            logger.warning("CTL200 controller was off - turning on...")
            self.controller.turn_on()

        logger.debug(f"Current = {self.current.get()}")

        return super().host_setup()

    @kernel
    def run_once(self):
        self.set_current(self.current.get())
        self.set_temperature(self.temperature.get())

        voltages = [0.0] * self.num_points.get()

        self.core.break_realtime()
        for i in range(0, self.num_points.get()):
            delay(SAMPLING_WAIT_TIME)
            voltages[i] = self.suservo_reader.read_adc()

        self.voltage.push(self.calculate_median(voltages))

    @rpc
    def calculate_median(self, list_of_floats) -> TFloat:
        return np.median(list_of_floats)

    @rpc
    def set_temperature(self, temperature):
        current_temperature_sp = self.controller.get_resistance_setpoint()
        current_temperature_actual = self.controller.get_resistance_actual()

        logger.debug("current_temperature_sp = %s", current_temperature_sp)
        logger.debug("current_temperature_actual = %s", current_temperature_actual)
        logger.debug("temperature = %s", temperature)

        temperature_setpoint_is_correct = round(current_temperature_sp, 2) == round(
            temperature, 2
        )

        if temperature_setpoint_is_correct and not (
            self.is_first_cycle and self.always_wait_at_start
        ):
            # ... then assume everything is fine and do nothing
            logger.debug("Temperature already at setpoint - continuing")
            return

        # Otherwise, set the temperature and wait for it
        logger.info(
            "Setting temperature to %s and waiting %ss",
            temperature,
            self.temperature_waittime.get(),
        )
        self.controller.set_resistance_setpoint(round(temperature, 2))
        time.sleep(self.temperature_waittime.get())

        self.is_first_cycle = False

    @rpc
    def set_current(self, current):
        self.controller.set_current_mA(1e3 * current)


ScanKoheronCurrent = make_fragment_scan_exp(ScanKoheronCurrentFrag)
