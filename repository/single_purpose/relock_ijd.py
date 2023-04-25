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

from repository.scan_koheron_current import ScanKoheronCurrentFrag


class RelockIJD1Frag(ExpFragment):
    """
    Relock IJD1
    """

    def build_fragment(self, *args, **kwargs) -> None:
        # Request the ijd controller device
        self.ijd_controller: CTL200 = self.get_device("blue_IJD1_controller")

        self.setattr_param(
            "v_increase_threshold",
            FloatParam,
            "Increase from minimum voltage that defines the upper end of the injection window",
            default=0.01,
        )
        self.v_increase_threshold: FloatParamHandle

        self.setattr_param(
            "i_jump_above_window",
            FloatParam,
            "How far above the window to jump when relocking",
            default=2 * 1e-3,
        )
        self.i_jump_above_window: FloatParamHandle

        self.setattr_param(
            "t_relock_waittime",
            FloatParam,
            "How long to wait after initial jump when relocking",
            default=5 * 1e-3,
        )
        self.t_relock_waittime: FloatParamHandle

        self.setattr_param(
            "i_start_scan",
            FloatParam,
            "Current to start scan",
            default=340 * 1e-3,
        )
        self.i_start_scan: FloatParamHandle

        self.setattr_param(
            "i_end_scan",
            FloatParam,
            "Current to end scan",
            default=310 * 1e-3,
        )
        self.i_end_scan: FloatParamHandle

        self.setattr_param(
            "num_points",
            FloatParam,
            "Number of scan points",
            default=100,
        )
        self.num_points: FloatParamHandle

        self.setattr_fragment("frag_ijd_scanner", ScanKoheronCurrentFrag)
        self.frag_ijd_scanner: ScanKoheronCurrentFrag

        setattr_subscan(
            self,
            "scan_ijd_current",
            self.frag_ijd_scanner,
            [(self.frag_ijd_scanner, "current")],
        )
        self.scan_ijd_current: Subscan

    def run_once(self) -> None:
        # scan over a range of currents on the IJD
        self.scan_ijd_current.run(
            [
                (
                    self.frag_ijd_scanner.current,
                    LinearGenerator(
                        self.start_current.get(),
                        self.stop_current.get(),
                        self.num_points.get(),
                        False,
                    ),
                )
            ]
        )
        # currents = []
        # voltages = []

        # # Find the optimum current
        # lock_point = self.find_lock_point(currents, voltages)

        # # Jump to it
        # self.ijd_controller.set_current(lock_point + self.i_jump_above_window.get())
        # time.sleep(self.t_relock_waittime.get())
        # self.ijd_controller.set_current(lock_point)

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
        for i in range(ind_biggest_diff, 0, -1):
            if voltage[i] > v_threshold:
                window_end = current[i + 1]
                break

        return (window_start + window_end) / 2


RelockIJD1 = make_fragment_scan_exp(RelockIJD1Frag)
