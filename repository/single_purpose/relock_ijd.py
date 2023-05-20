import logging
import time
from typing import List
from typing import Optional

from artiq.experiment import EnvExperiment
from artiq.experiment import portable
from artiq.experiment import TList
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import LinearGenerator
from ndscan.experiment import setattr_subscan
from ndscan.experiment import Subscan
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib.constants import IJD_DEFAULTS
from repository.scan_koheron_current import ScanKoheronCurrentFrag

logger = logging.getLogger(__name__)


class RelockIJDFrag(ExpFragment):
    """
    Relock one injected diode
    """

    def build_fragment(
        self, controller_name: Optional[str] = None, *args, **kwargs
    ) -> None:
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
            default=3 * 1e-3,
            unit="mA",
        )
        self.i_jump_above_window: FloatParamHandle

        self.setattr_param(
            "t_relock_waittime",
            FloatParam,
            "How long to wait after initial jump when relocking",
            unit="ms",
            default=300 * 1e-3,
        )
        self.t_relock_waittime: FloatParamHandle

        self.setattr_param(
            "i_start_scan",
            FloatParam,
            "Current to start scan",
            unit="mA",
            default=340 * 1e-3,
        )
        self.i_start_scan: FloatParamHandle

        self.setattr_param(
            "i_end_scan",
            FloatParam,
            "Current to end scan",
            unit="mA",
            default=320 * 1e-3,
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

        self.setattr_fragment(
            "frag_ijd_scanner", ScanKoheronCurrentFrag, controller_name=controller_name
        )
        self.frag_ijd_scanner: ScanKoheronCurrentFrag

        setattr_subscan(
            self,
            "scan_ijd_current",
            self.frag_ijd_scanner,
            [(self.frag_ijd_scanner, "current")],
        )
        self.scan_ijd_current: Subscan

    def host_setup(self):
        super().host_setup()

        # Request the ijd controller device
        self.ijd_controller: CTL200 = self.frag_ijd_scanner.controller

    def run_once(self) -> None:
        self.relock()

    def relock(self) -> None:
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
        lock_point = self.find_lock_point(currents, voltages)  # type: ignore
        start_point = lock_point + self.i_jump_above_window.get()
        t_wait = self.t_relock_waittime.get()

        # Jump to it
        logger.debug("Prelock - Setting I = %.2f mA", start_point * 1e3)
        self.ijd_controller.set_current_mA(start_point * 1e3)  # type: ignore

        logger.debug("Sleeping for %.3f s", t_wait)
        time.sleep(t_wait)

        logger.info("Lock - Setting I = %.2f mA", lock_point * 1e3)
        self.ijd_controller.set_current_mA(lock_point * 1e3)  # type: ignore

    @portable
    def find_lock_point(self, current: TList, voltage: TList):
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

        return (
            window_start + (window_end - window_start) * self.frac_through_window.get()
        )


class RelockAllIJDsFrag(ExpFragment):
    """
    Relock all IJDs
    """

    def build_fragment(self) -> None:
        ijd_controller_names = [
            "blue_IJD1_controller",
            "blue_IJD2_controller",
            "blue_IJD3_controller",
        ]

        self.ijd_controller_frags: List[RelockIJDFrag] = []

        # Request a relock fragment for each IJD controller
        for ijd_controller_name in ijd_controller_names:
            fragment_name = f"frag_relocker_{ijd_controller_name}"

            frag = self.setattr_fragment(
                fragment_name,
                RelockIJDFrag,
                ijd_controller_name,
            )

            self.ijd_controller_frags.append(frag)  # type: ignore

        # Create top-level parameters which will override the
        # subfragment's parameters
        self.setattr_param_like("num_points", self.ijd_controller_frags[0], default=40)
        self.setattr_param_like(
            "current_waittime",
            self.ijd_controller_frags[0].frag_ijd_scanner,
            default=100e-3,
        )
        self.num_points: FloatParamHandle
        self.current_waittime: FloatParamHandle

        # For each subfragment relocked, rebind parameters to set defaults for
        # each IJD
        for frag, ijd_controller_name in zip(
            self.ijd_controller_frags, ijd_controller_names
        ):
            default_temperature, default_window_position = IJD_DEFAULTS[
                ijd_controller_name
            ]

            frag.bind_param("num_points", self.num_points)

            self.setattr_param_rebind(
                f"{ijd_controller_name}_start_current",
                frag,
                original_name="i_start_scan",
                default=default_window_position + 5e-3,
            )

            self.setattr_param_rebind(
                f"{ijd_controller_name}_end_current",
                frag,
                original_name="i_end_scan",
                default=default_window_position - 2e-3,
            )

            self.setattr_param_rebind(
                f"{ijd_controller_name}_temperature",
                frag.frag_ijd_scanner,
                original_name="temperature",
                default=default_temperature,
            )

            # Disable waiting for temperature to settle - the relock algorithm
            # will just have to be run again if it fails because of temperature
            # and we don't want to delay the other IJDs
            frag.frag_ijd_scanner.override_param("temperature_waittime", 0)

        self.frag_relocker_blue_IJD1_controller: RelockIJDFrag

    def run_once(self) -> None:
        # Relock each IJD in order
        for ijd_relock_frag in self.ijd_controller_frags:
            ijd_relock_frag: RelockIJDFrag
            ijd_relock_frag.relock()


RelockSingleIJD = make_fragment_scan_exp(RelockIJDFrag)
RelockAllIJDs = make_fragment_scan_exp(RelockAllIJDsFrag)
