"""
TODO: Pass IJDSettings into Relock single IJD instead of rebinding parameters
"""

import logging
import time
from typing import List
from typing import Optional
from typing import Tuple

from artiq.coredevice.core import Core
from artiq.experiment import TList
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import ExpFragment
from ndscan.experiment import LinearGenerator
from ndscan.experiment import Subscan
from ndscan.experiment import setattr_subscan
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

import repository.lib.constants as constants
from repository.injected_diodes.relocker_board import RelockerChannelFrag
from repository.injected_diodes.set_koheron_controller import SetKoheronFrag
from repository.lib.constants import IJD_DEFAULTS
from repository.lib.constants import IJD_RELOCKER_DEFAULTS
from repository.lib.fragments.pyaion_overrides.default_beam_setter_override import (
    make_set_beams_to_default,
)

# from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class RelockIJDFrag(ExpFragment):
    """
    Relock one injected diode
    """

    def build_fragment(
        self,
        controller_name: Optional[str] = None,
        *args,
        **kwargs,
    ) -> None:
        if controller_name:
            defaults = IJD_DEFAULTS[controller_name]
        else:
            defaults = constants.IJDSettings(8800, 340e-3, 320e-3, 3e-3)

        self.setattr_param(
            "v_increase_threshold",
            FloatParam,
            "Increase from minimum voltage that defines the upper end of the injection window",
            default=0.01,
            unit="mV",
        )
        self.v_increase_threshold: FloatParamHandle

        self.setattr_param(
            "i_jump_above_window",
            FloatParam,
            "How far above the window to jump when relocking",
            default=defaults.relock_step,
            unit="mA",
        )
        self.i_jump_above_window: FloatParamHandle

        self.setattr_param(
            "t_relock_waittime",
            FloatParam,
            "How long to wait after initial jump when relocking",
            unit="s",
            default=defaults.relock_waittime,
        )
        self.t_relock_waittime: FloatParamHandle

        self.setattr_param(
            "i_start_scan",
            FloatParam,
            "Current to start scan",
            unit="mA",
            default=defaults.window_high,
        )
        self.i_start_scan: FloatParamHandle

        self.setattr_param(
            "i_end_scan",
            FloatParam,
            "Current to end scan",
            unit="mA",
            default=defaults.window_low,
        )
        self.i_end_scan: FloatParamHandle

        self.setattr_param(
            "num_points",
            IntParam,
            "Number of scan points",
            default=100,
        )
        self.num_points: IntParamHandle

        self.setattr_param(
            "frac_through_window",
            FloatParam,
            "Fraction of the way through the window to lock at",
            default=0.75,
            min=0,
            max=1,
        )
        self.frac_through_window: IntParamHandle

        self.frag_ijd_scanner: SetKoheronFrag = self.setattr_fragment(
            f"frag_koheron_{controller_name}",
            SetKoheronFrag,
            controller_name=controller_name,
            analysis_fn=self.find_lock_point,
        )
        for k, v in IJD_RELOCKER_DEFAULTS.items():
            if v.associated_controller == controller_name:
                self.relocker_frag: RelockerChannelFrag = self.setattr_fragment(
                    f"frag_{k}", RelockerChannelFrag, k
                )

        setattr_subscan(
            self,
            "scan_ijd_current",
            self.frag_ijd_scanner,
            [(self.frag_ijd_scanner, "current")],
        )
        self.scan_ijd_current: Subscan

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_device("core")
        self.core: Core

        self.controller_name = controller_name
        beam_infos = []
        if controller_name and (
            beam_names := IJD_DEFAULTS[controller_name].associated_beams
        ):
            logger.info("Adding %s to beam setter for %s", beam_names, self)
            beam_infos += [constants.URUKULED_BEAMS[b] for b in beam_names]

        self.beam_setter = self.setattr_fragment(
            "beam_setter",
            make_set_beams_to_default(
                urukul_beam_infos=beam_infos,
                use_automatic_setup=True,
                use_automatic_turnon=True,
            ),
        )

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

    def host_setup(self):
        super().host_setup()

        # Request the ijd controller device
        self.ijd_controller: CTL200 = self.frag_ijd_scanner.controller

    def run_once(self) -> None:
        self.device_setup()
        self.relock()

    def relock(self, enable_auto_relock=False) -> None:
        auto_relocking = self.relocker_frag.get_auto_relock()
        if auto_relocking:
            self.relocker_frag.set_auto_relock(False)
        self.relocker_frag.set_dac_voltage(0)

        self.relocker_frag.set_auto_relock(False)
        # scan over a range of currents on the IJD
        coordinates, values, analysis_results = self.scan_ijd_current.run(  # type: ignore
            [
                (
                    self.frag_ijd_scanner.current,
                    LinearGenerator(
                        self.i_start_scan.get(),
                        self.i_end_scan.get(),
                        self.num_points.get(),
                        False,
                    ),
                )
            ]
        )
        logger.debug("coordinates")
        logger.debug(coordinates)
        logger.debug("values")
        logger.debug(values)
        logger.debug("analysis_results")
        logger.debug(analysis_results)

        currents = coordinates[self.frag_ijd_scanner.current]
        logger.debug("currents")
        logger.debug(currents)

        voltages = values[self.frag_ijd_scanner.voltage]
        logger.debug("voltages")
        logger.debug(voltages)

        # Find the optimum current
        lock_point, window_start, window_end, v_window_start = self.find_lock_point(currents, voltages)  # type: ignore
        start_point = lock_point + self.i_jump_above_window.get()
        t_wait = self.t_relock_waittime.get()

        # Jump to it
        logger.debug("Prelock - Setting I = %.2f mA", start_point * 1e3)
        self.ijd_controller.set_current_mA(start_point * 1e3)  # type: ignore

        logger.debug("Sleeping for %.3f s", t_wait)
        time.sleep(t_wait)

        logger.info("Lock - Setting I = %.2f mA", lock_point * 1e3)
        self.ijd_controller.set_current_mA(lock_point * 1e3)  # type: ignore

        # Log action
        self.influx_logger.write(
            tags={
                "type": self.__class__.__name__,
                "controller": self.controller_name,
                "rid": self.scheduler.rid,
            },
            fields={
                "i_lock": lock_point,
                "i_start": window_start,
                "i_end": window_end,
                "i_window_size": window_end - window_start,
                "v_window": v_window_start,
            },
        )
        if enable_auto_relock or auto_relocking:
            self.relocker_frag.set_auto_relock(True)

    @portable
    def find_lock_point(
        self, current: TList, voltage: TList
    ) -> Tuple[float, float, float, float]:
        """
        Datapoints should be in descending order of current
        """

        # Find start of the window (low current end):
        biggest_diff = 0
        ind_biggest_diff = 0
        for i in range(len(current) - 1):  # type: ignore
            diff = voltage[i + 1] - voltage[i]
            if diff > biggest_diff:
                biggest_diff = diff
                ind_biggest_diff = i

        window_start = current[ind_biggest_diff]

        # Find end of window (i.e point before the voltage raises by v_increase_threshold)
        v_window_start = voltage[ind_biggest_diff]
        v_threshold = v_window_start + self.v_increase_threshold.get()
        window_end = current[0]
        for i in range(ind_biggest_diff, 0, -1):
            if voltage[i] > v_threshold:
                window_end = current[i + 1]
                break

        logger.debug("window_start=%.3f, window_end=%.3f", window_start, window_end)

        return (
            window_start + (window_end - window_start) * self.frac_through_window.get(),
            window_start,
            window_end,
            v_window_start,
        )


class RelockAllIJDsFrag(ExpFragment):
    """
    Relock all IJDs
    """

    def build_fragment(self) -> None:
        self.ijd_controller_frags: List[RelockIJDFrag] = []
        self.ijd_controller_enabled: List[BoolParamHandle] = []

        # Request a relock fragment for each IJD controller

        for ijd_controller_name in IJD_DEFAULTS:
            fragment_name = f"frag_relocker_{ijd_controller_name}"

            frag = self.setattr_fragment(
                fragment_name,
                RelockIJDFrag,
                ijd_controller_name,
            )

            self.ijd_controller_enabled.append(
                self.setattr_param(
                    f"{ijd_controller_name}_enabled",
                    BoolParam,
                    description=f"{ijd_controller_name} enabled",
                    default=True,
                )
            )
            self.ijd_controller_frags.append(frag)  # frag.frag_ijd type: ignore

            if len(self.ijd_controller_frags) == 1:
                self.setattr_param_like(
                    "num_points", self.ijd_controller_frags[0], default=100
                )
                self.setattr_param_like(
                    "current_waittime",
                    self.ijd_controller_frags[0].frag_ijd_scanner,
                    default=5e-3,
                )
                self.num_points: FloatParamHandle
                self.current_waittime: FloatParamHandle
            # Disable waiting for temperature to settle - the relock algorithm
            # will just have to be run again if it fails because of temperature
            # and we don't want to delay the other IJDs
            frag.frag_ijd_scanner.override_param("temperature_waittime", 0)
            frag.bind_param("num_points", self.num_points)
            frag.frag_ijd_scanner.bind_param("current_waittime", self.current_waittime)

        self.frag_relocker_red_IJD1_controller: RelockIJDFrag
        prev_default = constants.URUKULED_BEAMS["red_doublepass_injection"]
        self.setattr_param_rebind(
            "red_aom_frequency",
            self.frag_relocker_red_IJD1_controller.beam_setter,
            f"frequency_{prev_default.name}",
            default=prev_default.frequency + constants.RED_IJD_RELOCK_FREQUENCY_BOOST,
        )

        self.setattr_param(
            "enable_auto_relocking",
            BoolParam,
            "Enable relocker board autorelocking",
            default=True,
        )
        self.enable_auto_relocking: BoolParamHandle

    def run_once(self) -> None:
        # Manually call the device_setup, since this is not a kernel function
        self.device_setup()

        # Relock each IJD in order
        for i in range(len(self.ijd_controller_frags)):
            ijd_relock_frag = self.ijd_controller_frags[i]
            enabled = self.ijd_controller_enabled[i]

            if enabled.get():
                ijd_relock_frag.relock(self.enable_auto_relocking.get())

    def get_default_analyses(self):
        return super().get_default_analyses()


# RelockSingleIJD = make_fragment_scan_exp(RelockIJDFrag)
RelockAllIJDs = make_fragment_scan_exp(RelockAllIJDsFrag)
