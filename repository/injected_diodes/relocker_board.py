import logging
from typing import List
from typing import Optional

import numpy as np
from ndscan.experiment import BoolParam
from ndscan.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from relocker_driver.driver import RelockerDriver

from repository.lib.constants import IJD_RELOCKER_DEFAULTS

logger = logging.getLogger(__name__)


class RelockerChannelFrag(ExpFragment):
    """Single relocker board channel"""

    def build_fragment(self, channel_name: Optional[str] = None):
        """
        Build this fragment

        If relocker_name is provided then this fragment use it.
        Otherwise, it will expose it as an ARTIQ argument (note, not an ndscan parameter) instead.
        """

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
            max=100,
        )
        self.n_steps: IntParamHandle

        self.setattr_param(
            "window_frac",
            FloatParam,
            description="window fraction",
            default=defaults.window_frac,
            min=0.0,
            max=1.0,
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
            IntParam,
            description="v set wait time",
            default=defaults.wait_time,
            min=0,
            max=100000,
        )
        self.wait_time: IntParamHandle

        self.setattr_param(
            "auto_relock",
            BoolParam,
            description="Enable auto relock",
            default=defaults.auto_relock,
        )
        self.auto_relock: BoolParamHandle

        # And define a results channel as output
        self.setattr_result("voltages", OpaqueChannel)
        self.voltages: OpaqueChannel

        self.setattr_result("result", OpaqueChannel)
        self.result: OpaqueChannel

    def host_setup(self):
        defaults = IJD_RELOCKER_DEFAULTS[self.channel_name]
        self.channel = defaults.channel
        self.relocker_name = defaults.board_name
        self.relocker: RelockerDriver = self.get_device(self.relocker_name)
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
        )

    def get_read_voltages(self):
        read_voltages = self.relocker.get_read_voltages(self.channel)
        self.voltages.push(read_voltages)
        return read_voltages

    def push_voltages_to_applet(self, read_voltages):
        set_voltages = self.get_scan_voltages()
        err = np.zeros_like(read_voltages)
        self.set_dataset(
            f"{self.relocker_name}_{self.channel}_read_voltages",
            np.array(read_voltages),
            broadcast=True,
            archive=False,
        )
        self.set_dataset("set_voltages", set_voltages, broadcast=True, archive=False)
        self.set_dataset("err", err, broadcast=True, archive=False)
        cmd = f"${{artiq_applet}}plot_xy {self.relocker_name}_{self.channel}_read_voltages --x set_voltages --fit read_voltages --error err"
        self.ccb.issue("create_applet", f"{self.channel_name} relocker", cmd)

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
        return self.relocker.get_scan_voltages(self.channel)

    def run_once(self):
        if self.write_settings.get():
            self.set_scan_settings()
            self.set_lock_settings()
        if self.relock_enabled.get():
            self.relock()
        read_voltages = self.get_read_voltages()
        self.push_voltages_to_applet(read_voltages)
        logger.info(self.get_result())
        logger.info(self.get_auto_relock_stats())


class RelockerFrag(ExpFragment):
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

            if enabled.get():
                if relocker_frag.write_settings:
                    relocker_frag.set_scan_settings()
                    relocker_frag.set_lock_settings()
                relocker_frag.relock()
                read_voltages = relocker_frag.get_read_voltages()
                relocker_frag.push_voltages_to_applet(read_voltages)
                result = relocker_frag.get_result()
                logger.info(result)


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


RunRelockerChannel = make_fragment_scan_exp(RelockerChannelFrag)
RunAllRelockers = make_fragment_scan_exp(RelockerFrag)
RelockerAuto = make_fragment_scan_exp(RelockerAutoFrag)
