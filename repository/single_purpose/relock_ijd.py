import logging
import time

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

from repository.scan_koheron_current import ScanKoheronCurrentFrag

logger = logging.getLogger(__name__)


class RelockIJD1Frag(ExpFragment):
    """
    Relock IJD1
    """

    def build_fragment(self, *args, **kwargs) -> None:

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
            default=2 * 1e-3,
            unit="mA",
        )
        self.i_jump_above_window: FloatParamHandle

        self.setattr_param(
            "t_relock_waittime",
            FloatParam,
            "How long to wait after initial jump when relocking",
            unit="ms",
            default=5 * 1e-3,
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
            default=310 * 1e-3,
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

        self.setattr_fragment("frag_ijd_scanner", ScanKoheronCurrentFrag)
        self.frag_ijd_scanner: ScanKoheronCurrentFrag

        # Request the ijd controller device
        self.ijd_controller: CTL200 = self.frag_ijd_scanner.controller

        setattr_subscan(
            self,
            "scan_ijd_current",
            self.frag_ijd_scanner,
            [(self.frag_ijd_scanner, "current")],
        )
        self.scan_ijd_current: Subscan

    def run_once(self) -> None:
        # scan over a range of currents on the IJD
        coordinates, values, analysis_results = self.scan_ijd_current.run(
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
        lock_point = self.find_lock_point(currents, voltages)
        start_point = lock_point + self.i_jump_above_window.get()
        t_wait = self.t_relock_waittime.get()

        # Jump to it
        logger.info("Prelock - Setting I = %.2f mA", start_point * 1e3)
        self.ijd_controller.set_current_mA(start_point * 1e3)

        logger.info("Sleeping for %.3f s", t_wait)
        time.sleep(t_wait)

        logger.info("Lock - Setting I = %.2f mA", lock_point * 1e3)
        self.ijd_controller.set_current_mA(lock_point * 1e3)

    @portable
    def find_lock_point(self, current: TList, voltage: TList):
        """
        Datapoints should be in descending order of current
        """

        # Find start of the window (low current end):
        biggest_diff = 0
        ind_biggest_diff = 0
        for i in range(len(current) - 1):
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


RelockIJD1 = make_fragment_scan_exp(RelockIJD1Frag)
