import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TList
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle

from device_db_config import get_all_configurations_from_db
from device_db_config.configuration import VoltageControlledCurrentSupply

logger = logging.getLogger(__name__)


class SetAnalogCurrentSupply(Fragment):
    """
    Set a current supply that's controlled by an analog voltage
    """

    def build_fragment(self, current_config: VoltageControlledCurrentSupply):
        self.setattr_device("core")
        self.core: Core

        self.current_config = current_config

        self.zotino = self.get_device(self.current_config.zotino)
        self.zotino: Zotino

        self.first_run = True
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            if self.debug_enabled:
                logger.info("Initiating Zotino %s", self.zotino)

            self.core.break_realtime()
            self.zotino.init()

            self.first_run = False

        self.device_setup_subfragments()

    @kernel
    def set_current(self, current):
        """
        Set a current in amps.

        This method does not advance the timeline but it does write SPI events
        into the past.
        """
        voltage = current / self.current_config.gain

        if self.debug_enabled:
            logger.info(
                "Setting current = %.2f with voltage = %.3f on channel %i",
                current,
                voltage,
                self.current_config.zotino_channel,
            )

        self.zotino.set_dac([voltage], [self.current_config.zotino_channel])


class SetAnalogCurrentSupplies(Fragment):
    """
    Set multiple current supplies that are controlled by a analog voltages.
    The supplies must all be controlled by the same Zotino
    """

    def build_fragment(self, current_configs: List[VoltageControlledCurrentSupply]):
        self.setattr_device("core")
        self.core: Core

        self.current_configs = current_configs

        assert all(
            [c.zotino == current_configs[0].zotino for c in current_configs]
        ), "All current drivers must use the same Zotino"

        self.zotino = self.get_device(self.current_configs[0].zotino)
        self.zotino: Zotino

        self.zotino_channels = [c.zotino_channel for c in current_configs]

        # %% Kernel variables
        self.first_run = True
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.num_supplies = len(current_configs)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "num_supplies",
            "current_configs",
            "zotino",
            "zotino_channels",
        }

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            if self.debug_enabled:
                logger.info("Initiating Zotino %s", self.zotino)

            self.core.break_realtime()
            self.zotino.init()

            self.first_run = False

        self.device_setup_subfragments()

    @portable
    def _single_current_to_volts(self, current: TFloat, current_supply_idx: TInt32):
        return current / self.current_configs[current_supply_idx].gain

    @portable
    def _currents_to_volts(self, currents: TList(TFloat), voltages_out: TList(TFloat)):
        if len(currents) != len(self.current_configs):
            raise ValueError("Wrong number of currents")

        if len(currents) != len(voltages_out):
            raise ValueError("Output array is wrong size")

        for i in range(len(self.current_configs)):
            voltages_out[i] = self._single_current_to_volts(currents[i], i)

    @kernel
    def set_currents(self, currents: TList(TFloat)):
        """
        Set currents in amps.

        This method does not advance the timeline but does require at least
        1.5us + 808ns * len(currents) on a Kasli 1.x as SPI events are written
        into the past.
        """

        voltages = [0.0] * len(self.current_configs)

        self._currents_to_volts(currents, voltages)

        if self.debug_enabled:
            logger.info(
                "Setting currents = %s with voltages = %s on channels %s",
                currents,
                voltages,
                self.zotino_channels,
            )

        self.zotino.set_dac(voltages, self.zotino_channels)

    @kernel
    def set_currents_ramping(
        self,
        currents_start: TList(TFloat),
        currents_end: TList(TFloat),
        duration: TFloat,
        ramp_step: TFloat = 1 / 75e3,
    ):
        """
        Queue a linear ramp of the currents controlled by this object

        This method will write lots of RTIO events for the `duration` of the
        ramp and will advance the timeline until the end of the ramp. It will
        also require quite a lot of time to compute and queue the ramp, so users
        should consider DMA if performance is limiting.

        Note that `time_step` will be approximate - this method will ensure that
        initial and final writes occurs at the start and end of the `duration`
        period, with `time_step` varied slightly to ensure that. Note also that
        this means you cannot immediately start a new ramp when the old one ends
        - it must be spaced at least one Zotino write away
        (`1.5us + 808ns * len(currents)` at time of writing).

        Args:
            currents_start (TList): List of starting currents / A

            currents_end (TList): List of ending currents / A

            duration (TFloat): Time to perform the ramp for

            ramp_step (TFloat, optional):
                Timestamp of RTIO writes / s. Defaults to `1/75e3` since the
                Zotino has a 75 kHz low-pass filter.
        """

        # Compute grid for writes
        num_points = 1 + int(duration // ramp_step)
        actual_time_step_mu = self.core.seconds_to_mu(duration / float(num_points))

        current_steps = [0.0] * self.num_supplies
        for i_supply in range(self.num_supplies):
            current_steps[i_supply] = (
                currents_end[i_supply] - currents_start[i_supply]
            ) / float(num_points - 1)

        # Here we convert the current steps to voltage steps. This assumes that
        # the current to voltage conversion function _currents_to_volts is
        # linear. If this is not true, this will break. This is tested in
        # `test_current_to_volts_convertion_is_linear`. We also assume that the
        # Zotino is linear, but that's not tested.
        voltage_steps_mu = [0.0] * self.num_supplies
        for i_supply in range(self.num_supplies):
            voltage_step = self._single_current_to_volts(
                current_steps[i_supply], i_supply
            )
            voltage_steps_mu[i_supply] = self.zotino.voltage_to_mu(voltage_step)

        # Now we queue the points, including an initial and final point
        voltages_now_mu = [0.0] * self.num_supplies
        for i_supply in range(self.num_supplies):
            initial_voltage = self._single_current_to_volts(
                currents_start[i_supply], i_supply
            )
            voltages_now_mu[i_supply] = self.zotino.voltage_to_mu(initial_voltage)

        for _ in range(num_points):
            # Set voltages
            self.zotino.set_dac_mu(voltages_now_mu, self.zotino_channels)

            # Calculate next voltages
            for i_supply in range(self.num_supplies):
                voltages_now_mu[i_supply] += voltage_steps_mu[i_supply]

            delay_mu(actual_time_step_mu)


class SetAnalogCurrentSupplyExpFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        current_configs = {
            k: v
            for k, v in get_all_configurations_from_db().items()
            if isinstance(v, VoltageControlledCurrentSupply)
        }

        self.setattr_argument(
            "current_supply",
            EnumerationValue(
                list(current_configs.keys()), default=list(current_configs.keys())[0]
            ),
        )
        self.current_supply: str

        if self.current_supply is not None:
            current_config = current_configs[self.current_supply]

        else:
            current_config = list(current_configs.values())[0]

        self.setattr_fragment("setter", SetAnalogCurrentSupply, current_config)
        self.setter: SetAnalogCurrentSupply

        self.setattr_param(
            "current", FloatParam, "Current to set", default=0.0, unit="A"
        )
        self.current: FloatParamHandle

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(10e-3)
        self.setter.set_current(self.current.get())


SetAnalogCurrentSupplyExp = make_fragment_scan_exp(SetAnalogCurrentSupplyExpFrag)
