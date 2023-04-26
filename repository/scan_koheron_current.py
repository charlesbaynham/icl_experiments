import logging
import time

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import SUServo
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue
from artiq.experiment import rpc
from artiq.experiment import TFloat
from artiq.experiment import us
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import BoolParam
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.lib.utils import get_local_devices

from repository.lib import constants
from repository.lib.fragments.read_adc import ReadADC
from repository.lib.fragments.read_adc import ReadSamplerADC
from repository.lib.fragments.read_adc import ReadSUServoADC


logger = logging.getLogger(__name__)


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
            "current_waittime",
            FloatParam,
            description="Time to wait after a current change",
            default=0,
            min=0,
            max=1000,
            unit="ms",
            step=1e-3,
        )
        self.current_waittime: FloatParamHandle

        self.setattr_param(
            "sampling_waittime",
            FloatParam,
            description="Time to wait between samples",
            default=1e-3,
            min=0,
            max=1,
            unit="ms",
            step=1e-4,
        )
        self.sampling_waittime: FloatParamHandle

        self.setattr_param(
            "num_points",
            IntParam,
            description="Number of voltage points to take, spaced by 1ms",
            default=10,
            min=1,
            max=1000,
        )
        self.num_points: IntParamHandle

        self.setattr_param(
            "aom_attenuation",
            FloatParam,
            description="Attenuation of injection AOM",
            default=20,
            min=18,
            max=30,
            unit="dB",
            step=0.1,
        )
        self.aom_attenuation: FloatParamHandle

        self.setattr_param(
            "change_aom",
            BoolParam,
            description="If False, ignore the injection AOM",
            default="False",
        )
        self.change_aom: BoolParamHandle

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

        # Get the passed controller's associated beat detection channel
        if self.controller_name is not None:  # i.e. not in build()
            try:
                self.adc_device, self.adc_channel = self.get_device_db()[
                    "IJD_monitors"
                ][self.controller_name]
            except KeyError:
                raise KeyError(
                    f"Could not find controller {self.controller_name} in device db. Have you added it to _aliases.py?"
                )

            # Load the sampler / suservo utility from pyaion
            adc_obj = self.get_device(self.adc_device)
            if isinstance(adc_obj, Sampler):
                self.setattr_fragment(
                    "adc_reader", ReadSamplerADC, adc_obj, self.adc_channel
                )
            elif isinstance(adc_obj, SUServo):
                self.setattr_fragment(
                    "adc_reader", ReadSUServoADC, adc_obj, self.adc_channel
                )
            else:
                raise ValueError(
                    f"Expected a SUServo or Sampler, received {self.adc_device}"
                )

        self.adc_reader: ReadADC

        self.setattr_fragment(
            "injection_aom_setter",
            LibSetSUServoStatic,
            "suservo_aom_doublepass_461_injection",
        )
        self.injection_aom_setter: LibSetSUServoStatic

        # And define a results channel as output
        self.setattr_result("voltage")
        self.voltage: ResultChannel

        self.print_debug_statements = logger.isEnabledFor(logging.DEBUG)
        self.is_first_cycle = True

        self.last_temperature: TFloat = -1.0
        self.last_current: TFloat = -1.0

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

        current_waittime = self.current_waittime.get()
        sampling_waittime = self.sampling_waittime.get()
        num_points = self.num_points.get()

        voltages = [0.0] * self.num_points.get()

        self.core.break_realtime()

        if self.change_aom.get():
            self.injection_aom_setter.set_suservo(
                constants.BLUE_INJECTION_AOM_DEFAULT_FREQUENCY,
                1.0,
                self.aom_attenuation.get(),
            )

        if current_waittime > 0.0:
            delay(current_waittime)

        for i in range(0, num_points):
            delay(sampling_waittime)
            voltages[i] = self.adc_reader.read_adc()

        self.voltage.push(self.calculate_median(voltages))

    @rpc
    def calculate_median(self, list_of_floats) -> TFloat:
        return np.median(list_of_floats)

    @kernel
    def set_temperature(self, temperature: TFloat):
        if (self.last_temperature != temperature) or (
            self.is_first_cycle and self.always_wait_at_start
        ):
            self.set_temperature_rpc(temperature)
            self.last_temperature = temperature

    @rpc
    def set_temperature_rpc(self, temperature):
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

    @kernel
    def set_current(self, current: TFloat):
        if self.last_current != current:
            self.set_current_rpc(current)
            self.last_current = current

    @rpc
    def set_current_rpc(self, current):
        self.controller.set_current_mA(1e3 * current)


ScanKoheronCurrent = make_fragment_scan_exp(ScanKoheronCurrentFrag)
