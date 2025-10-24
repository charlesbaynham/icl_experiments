import logging
import time
from typing import List
from typing import Optional

import numpy as np
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import BoolParam
from ndscan.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from relocker_driver.driver import RelockerDriver

from device_db_config import get_configuration_from_db
from repository.lib.constants import IJD_RELOCKER_DEFAULTS
from repository.lib.constants import SCANNER_BOARD_DEFAULTS
from repository.lib.constants import IJDRelockerSettings
from repository.lib.constants import ScannerBoardSettings

logger = logging.getLogger(__name__)


class RelockerChannelFrag(ExpFragment):
    """Single relocker board channel"""

    def build_fragment(self, channel_name: Optional[str] = None):
        """
        Build this fragment

        If relocker_name is provided then this fragment use it.
        Otherwise, it will expose it as an ARTIQ argument (note, not an ndscan parameter) instead.
        """

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_device("ccb")
        if channel_name:
            self.channel_name = channel_name
            defaults = IJD_RELOCKER_DEFAULTS[channel_name]
        else:
            channel_names = list(IJD_RELOCKER_DEFAULTS.keys())
            self.setattr_argument(
                "channel_name",
                EnumerationValue(channel_names, default=channel_names[0]),
            )
            self.channel_name: str
            defaults = IJD_RELOCKER_DEFAULTS["red_IJD1_relocker"]

        self.setattr_param(
            "relock_enabled", BoolParam, description="Relock?", default=False
        )
        self.relock_enabled: BoolParamHandle

        self.setattr_param(
            "write_settings",
            BoolParam,
            description="Write settings",
            default=False,
        )
        self.write_settings: BoolParamHandle

        self.setattr_param(
            "v_min",
            FloatParam,
            description="v_min",
            default=defaults.v_min,
            min=-4.0,
            max=4.0,
            unit="Volts",
            scale=1,
            step=0.01,
        )
        self.v_min: FloatParamHandle

        self.setattr_param(
            "v_max",
            FloatParam,
            description="v_max",
            default=defaults.v_max,
            min=-4.0,
            max=4.0,
            unit="Volts",
            scale=1,
            step=0.01,
        )
        self.v_max: FloatParamHandle

        self.setattr_param(
            "n_steps",
            IntParam,
            description="n steps",
            default=defaults.n_steps,
            min=10,
            max=128,
        )
        self.n_steps: IntParamHandle

        self.setattr_param(
            "window_frac",
            FloatParam,
            description="window fraction",
            default=defaults.window_frac,
            scale=1,
            step=0.01,
        )
        self.window_frac: FloatParamHandle

        self.setattr_param(
            "min_diff",
            FloatParam,
            description="min biggest diff",
            default=defaults.min_diff,
            min=0.0,
            max=5.0,
            scale=1,
            step=0.01,
        )
        self.min_diff: FloatParamHandle

        self.setattr_param(
            "v_low_threshold",
            FloatParam,
            description="lowest voltage threshold",
            default=defaults.v_low_threshold,
            min=-1.0,
            max=4.0,
            scale=1,
            step=0.01,
        )
        self.v_low_threshold: FloatParamHandle

        self.setattr_param(
            "v_rise_threshold",
            FloatParam,
            description="voltage increase threshold",
            default=defaults.v_rise_threshold,
            min=0.0,
            max=4.0,
            scale=1,
            step=0.01,
        )
        self.v_rise_threshold: FloatParamHandle

        self.setattr_param(
            "wait_time",
            FloatParam,
            description="v set wait time",
            default=defaults.wait_time,
            min=0.0,
            unit="s",
        )
        self.wait_time: FloatParamHandle

        self.setattr_param(
            "wait_time_per_scan_step",
            FloatParam,
            description="wait time per scan step",
            default=0.001,
            min=0.0,
            unit="us",
        )
        self.wait_time_per_scan_step: FloatParamHandle

        self.setattr_param(
            "auto_relock",
            BoolParam,
            description="Enable auto relock",
            default=defaults.auto_relock,
        )
        self.auto_relock: BoolParamHandle

        self.setattr_param(
            "v_relock_step_up",
            FloatParam,
            description="voltage step up on relock",
            default=defaults.v_relock_step_up,
            min=0.0,
            max=5.0,
            unit="V",
        )
        self.v_relock_step_up: FloatParamHandle

        self.setattr_param(
            "alpha_denominator",
            IntParam,
            description="Smoothing factor for averaging. Bigger = more smoothing",
            default=defaults.alpha_denominator,
            min=0,
            max=2**31,
        )
        self.alpha_denominator: IntParamHandle

        # And define a results channel as output
        self.setattr_result("read_voltages", OpaqueChannel)
        self.read_voltages: OpaqueChannel

        self.setattr_result("set_voltages", OpaqueChannel)
        self.set_voltages: OpaqueChannel

        self.setattr_result("result", OpaqueChannel)
        self.result: OpaqueChannel

        self.setattr_result("i_biggest_diff", FloatChannel, unit="mA")
        self.i_biggest_diff: FloatChannel

        self.setattr_result("i_rise", FloatChannel, unit="mA")
        self.i_rise: FloatChannel

    def host_setup(self):
        defaults = IJD_RELOCKER_DEFAULTS[self.channel_name]
        self.channel = defaults.channel
        self.relocker_name = defaults.board_name
        self.relocker: RelockerDriver = self.get_device(self.relocker_name)

        self.controller_name = defaults.associated_controller
        self.controller: CTL200 = self.get_device(self.controller_name)

        return super().host_setup()

    def set_scan_settings(self):
        self.relocker.set_scan_settings(
            self.channel,
            self.v_min.get(),
            self.v_max.get(),
            self.n_steps.get(),
        )

    def set_lock_settings(self):
        self.relocker.set_lock_settings(
            self.channel,
            self.window_frac.get(),
            self.min_diff.get(),
            self.v_low_threshold.get(),
            self.v_rise_threshold.get(),
            self.wait_time.get(),
            self.auto_relock.get(),
            self.v_relock_step_up.get(),
            self.alpha_denominator.get(),
            scan_step_delay=self.wait_time_per_scan_step.get(),
        )

    def get_read_voltages(self):
        read_voltages = self.relocker.get_read_voltages(self.channel)
        self.read_voltages.push(read_voltages)
        return read_voltages

    def get_result(self):
        result = self.relocker.get_result(self.channel)
        self.result.push(result)
        return result

    def relock(self):
        self.relocker.relock(self.channel)

    def get_auto_relock(self):
        return self.relocker.get_auto(self.channel)

    def set_auto_relock(self, auto: bool):
        self.relocker.set_auto(self.channel, auto)

    def set_dac_voltage(self, v):
        self.relocker.set_dac_ch(self.channel, v)

    def get_auto_relock_stats(self):
        return self.relocker.get_auto_relock_stats(self.channel)

    def get_scan_voltages(self):
        set_voltages = self.relocker.get_scan_voltages(self.channel)
        self.set_voltages.push(set_voltages)
        return set_voltages

    def get_scan_currents(self, scan_voltages):
        info = get_configuration_from_db("IJD_info")[self.controller_name]
        current_gain = info["mod_gain"]
        input_resistance = info["input_resistance"]
        output_resistance = info["output_resistance"]
        voltage_ratio = input_resistance / (input_resistance + output_resistance)
        logger.info("current gain: %s", current_gain)
        current_act = self.controller.get_current_mA()
        logger.info("current act: %s", current_act)
        return np.array(
            [
                v * voltage_ratio * current_gain * 1e3 + current_act
                for v in scan_voltages
            ]
        )

    def log_results(self):
        # Log action
        results = self.get_result()
        result_labelled = self.relocker.get_result_labelled(self.channel)
        scan_voltages = self.get_scan_voltages()[::-1]
        scan_voltages = self.get_scan_currents(scan_voltages)

        self.i_rise.push(1e-3 * scan_voltages[result_labelled.i_rise])
        self.i_biggest_diff.push(1e-3 * scan_voltages[result_labelled.i_biggest_diff])

        read_voltages = self.get_read_voltages()
        logger.info(results)

        i_start = int(results[0])
        i_end = int(results[1])
        i_lock = int(results[2])
        if i_lock >= len(read_voltages):
            i_lock = len(read_voltages) - 1

        # window_start = scan_currents[i_start]
        # window_end = scan_currents[i_end]
        # lock_point = scan_currents[i_lock]

        err = np.zeros_like(read_voltages)
        self.set_dataset(
            f"{self.relocker_name}_{self.channel}_read_voltages",
            np.array(read_voltages),
            broadcast=True,
            archive=False,
        )

        # self.set_dataset(
        #     f"{self.relocker_name}_{self.channel}_set_currents",
        #     scan_currents,
        #     broadcast=True,
        #     archive=False,
        # )
        self.set_dataset(
            f"{self.relocker_name}_{self.channel}_set_voltages",
            np.array(scan_voltages),
            broadcast=True,
            archive=False,
        )
        self.set_dataset(
            "err",
            err,
            broadcast=True,
            archive=False,
        )
        window = [i_start, i_end, i_lock, read_voltages[i_lock]]
        self.set_dataset(
            f"{self.relocker_name}_{self.channel}_window",
            window,
            broadcast=True,
            archive=False,
        )
        cmd = f"${{artiq_applet}}plot_xy {self.relocker_name}_{self.channel}_read_voltages --x {self.relocker_name}_{self.channel}_set_voltages"
        cmd = f"${{python}} -m repository.lib.applets.ijd_window_applet {self.relocker_name}_{self.channel}_read_voltages {self.relocker_name}_{self.channel}_set_voltages  {self.relocker_name}_{self.channel}_window --x_label 'Current (mA)'"

        self.ccb.issue("create_applet", f"{self.channel_name} relocker", cmd)
        logger.info("window_start: %s", i_start)
        logger.info("window_end: %s", i_end)
        logger.info("lock_point: %s", i_lock)
        # self.influx_logger.write(
        #     tags={
        #         "type": self.__class__.__name__,
        #         "controller": self.relocker_name,
        #         "channel": self.channel,
        #         "rid": self.scheduler.rid,
        #     },
        #     fields={
        #         "i_lock": lock_point,
        #         "i_start": window_start,
        #         "i_end": window_end,
        #         "i_window_size": window_end - window_start,
        #     },
        # )

    def run_once(self):
        if self.write_settings.get():
            self.set_scan_settings()
            self.set_lock_settings()
        if self.relock_enabled.get():
            self.relock()
        self.log_results()


class AllRelockersFrag(ExpFragment):
    def build_fragment(self):
        self.relocker_frags: List[RelockerChannelFrag] = []
        self.relocker_enabled: List[BoolParamHandle] = []

        for ijd_name in IJD_RELOCKER_DEFAULTS:
            IJD_RELOCKER_DEFAULTS[ijd_name]
            fragment_name = f"frag_relocker_{ijd_name}"

            frag = self.setattr_fragment(
                fragment_name,
                RelockerChannelFrag,
                ijd_name,
            )

            self.relocker_frags.append(frag)  # frag.frag_ijd type: ignore

            self.relocker_enabled.append(
                self.setattr_param(
                    f"{ijd_name}_enabled",
                    BoolParam,
                    description=f"{ijd_name} enabled",
                    default=True,
                )
            )

        self.setattr_param(
            "write_settings",
            BoolParam,
            description="Write settings",
            default=True,
        )
        self.write_settings: BoolParamHandle

        self.setattr_param(
            "log_results",
            BoolParam,
            description="Log if no relock",
            default=False,
        )
        self.log_results: BoolParamHandle

        for i, relocker in enumerate(self.relocker_frags):
            relocker.bind_param("relock_enabled", self.relocker_enabled[i])
            relocker.bind_param("write_settings", self.write_settings)

    def run_once(self) -> None:
        for i, relocker in enumerate(self.relocker_frags):
            if self.relocker_enabled[i].get():
                relocker.run_once()
            else:
                if self.log_results.get():
                    relocker.log_results()


class RelockerAutoFrag(ExpFragment):
    "Enable relocker autorelocking"

    def build_fragment(self):
        self.relocker_frags: List[RelockerChannelFrag] = []
        self.relocker_enabled: List[BoolParamHandle] = []

        for ijd_name in IJD_RELOCKER_DEFAULTS:
            IJD_RELOCKER_DEFAULTS[ijd_name]
            fragment_name = f"frag_relocker_{ijd_name}"

            frag = self.setattr_fragment(
                fragment_name,
                RelockerChannelFrag,
                ijd_name,
            )

            self.relocker_frags.append(frag)  # frag.frag_ijd type: ignore

            self.relocker_enabled.append(
                self.setattr_param(
                    f"{ijd_name}_enabled",
                    BoolParam,
                    description=f"{ijd_name} enabled",
                    default=True,
                )
            )

    def run_once(self) -> None:
        for i in range(len(self.relocker_frags)):
            relocker_frag = self.relocker_frags[i]
            enabled = self.relocker_enabled[i]

            relocker_frag.set_auto_relock(enabled.get())


class ScanIJDRelockerFrag(ExpFragment):
    def build_fragment(self, channel_name: Optional[str] = None):
        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_device("ccb")
        if channel_name:
            self.channel_name = channel_name
            defaults = IJD_RELOCKER_DEFAULTS[channel_name]
        else:
            channel_names = list(IJD_RELOCKER_DEFAULTS.keys())
            channel_names += list(SCANNER_BOARD_DEFAULTS.keys())
            self.setattr_argument(
                "channel_name",
                EnumerationValue(channel_names, default=channel_names[0]),
            )
            self.channel_name: str
            defaults = IJD_RELOCKER_DEFAULTS["red_IJD1_relocker"]

        self.setattr_param(
            "v_min",
            FloatParam,
            description="v min",
            default=defaults.v_min,
            unit="V",
            min=-4.0,
            max=4.0,
        )
        self.v_min: FloatParamHandle

        self.setattr_param(
            "v_max",
            FloatParam,
            description="v max",
            default=defaults.v_max,
            unit="V",
            min=-4.0,
            max=4.0,
        )
        self.v_max: FloatParamHandle

        self.setattr_param(
            "v_step",
            FloatParam,
            description="voltage step",
            default=0.01,
            unit="V",
        )
        self.v_step: FloatParamHandle

        self.setattr_param(
            "freq", FloatParam, description="frequency", default=1, unit="Hz"
        )
        self.freq: FloatParamHandle

        # self.setattr_param(
        #     "time_to_scan",
        #     IntParam,
        #     description="time to leave scan running",
        #     default=10,
        #     unit="s",
        # )
        # self.time_to_scan: IntParamHandle

    def host_setup(self):
        defaults_dict = {**IJD_RELOCKER_DEFAULTS, **SCANNER_BOARD_DEFAULTS}
        defaults: IJDRelockerSettings | ScannerBoardSettings = defaults_dict[
            self.channel_name
        ]
        self.channel = defaults.channel
        self.relocker_name = defaults.board_name
        self.relocker: RelockerDriver = self.get_device(self.relocker_name)
        super().host_setup()

    def start_scan(self):
        cmd = f"SCAN {self.channel} {self.v_min.get()} {self.v_max.get()} {self.v_step.get()} {self.freq.get()}"
        self.relocker.write(cmd)

    def cancel_scan(self):
        self.relocker.cancel_command()
        logger.info(self.relocker.read_line())
        logger.info(self.relocker.read_line())

    # def run_once(self):

    #     self.relocker.scan(
    #         self.channel,
    #         self.v_min.get(),
    #         self.v_max.get(),
    #         self.v_step.get(),
    #         self.freq.get(),
    #     )

    #     while True:
    #         time.sleep(1)
    #         if self.scheduler.check_termination(self.scheduler.rid):
    #             break
    #     self.cleanup()

    def run_once(self):
        self.start_scan()
        while True:
            time.sleep(1)
            if self.scheduler.check_termination(self.scheduler.rid):
                break
        self.cancel_scan()

    def cleanup(self):
        logger.info("Cancelling scan")
        self.relocker.cancel_command()


RunRelockerChannel = make_fragment_scan_exp(RelockerChannelFrag)
AllRelockers = make_fragment_scan_exp(AllRelockersFrag)
RelockerAuto = make_fragment_scan_exp(RelockerAutoFrag)
ScanIJDRelocker = make_fragment_scan_exp(ScanIJDRelockerFrag)
