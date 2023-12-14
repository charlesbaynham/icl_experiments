import random
import time

import numpy as np
from ndscan.experiment import *
from oitg.errorbars import binom_onesided


class Readout(Fragment):
    def build_fragment(self):
        self.setattr_param(
            "num_shots", IntParam, "Number of shots", 100, is_scannable=False
        )
        self.setattr_param(
            "mean_0", FloatParam, "Dark counts over readout duration", 0.1
        )
        self.setattr_param(
            "mean_1", FloatParam, "Bright counts over readout duration", 20.0
        )
        self.setattr_param("threshold", IntParam, "Threshold", 5)

        self.setattr_result("counts", OpaqueChannel)
        self.setattr_result("p")
        self.setattr_result("p_err", display_hints={"error_bar_for": self.p.path})

    def simulate_shots(self, p):
        num_shots = self.num_shots.get()

        counts = np.empty(num_shots, dtype=np.int16)
        for i in range(num_shots):
            mean = self.mean_0.get() if random.random() > p else self.mean_1.get()
            counts[i] = np.random.poisson(mean)
        self.counts.push(counts)

        num_brights = np.sum(counts >= self.threshold.get())
        p, p_err = binom_onesided(num_brights, num_shots)
        self.p.push(p)
        self.p_err.push(p_err)


class RabiFlopSim(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("readout", Readout)

        self.setattr_param(
            "rabi_freq", FloatParam, "Rabi frequency", 1.0 * MHz, unit="MHz", min=0.0
        )
        self.setattr_param(
            "duration", FloatParam, "Pulse duration", 0.5 * us, unit="us", min=0.0
        )
        self.setattr_param("detuning", FloatParam, "Detuning", 0.0 * MHz, unit="MHz")

    def run_once(self):
        omega0 = 2 * np.pi * self.rabi_freq.get()
        delta = 2 * np.pi * self.detuning.get()
        omega = np.sqrt(omega0**2 + delta**2)
        p = 1 - (omega0 / omega * np.sin(omega / 2 * self.duration.get())) ** 2
        self.readout.simulate_shots(p)
        time.sleep(0.01)

    def get_default_analyses(self):
        return [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.duration,
                    "y": self.readout.p,
                    "y_err": self.readout.p_err,
                },
                constants={
                    "t_dead": 0,
                },
            )
        ]


ScanRabiFlopSim = make_fragment_scan_exp(RabiFlopSim)


##################


"""
Shows how a simple experiment can be extended with custom fitting code, and used as a
subscan from other fragments.
"""
from ndscan.experiment import *
import oitg.fitting
from rabi_flop import RabiFlopSim


class RabiFlopWithAnalysis(RabiFlopSim):
    """Rabi flop example, extended by a custom default analysis and fit procedure

    (Usually, get_default_analyses() would directly be defined in the respective
    ExpFragment; we just extend RabiFlopSim here to avoid code duplication while keeping
    the other example simple.)
    """

    def get_default_analyses(self):
        return [
            CustomAnalysis(
                [self.duration],
                self._analyse_time_scan,
                [
                    OpaqueChannel("fit_xs"),
                    OpaqueChannel("fit_ys"),
                    FloatChannel("t_pi", "Fitted π time", unit="us"),
                    FloatChannel("t_pi_err", "Fitted π time error", unit="us"),
                ],
            )
        ]

    def _analyse_time_scan(self, axis_values, result_values, analysis_results):
        x = axis_values[self.duration]
        y = result_values[self.readout.p]
        y_err = result_values[self.readout.p_err]

        fit_results, fit_errs, fit_xs, fit_ys = oitg.fitting.sinusoid.fit(
            x, y, y_err, evaluate_function=True, evaluate_n=100
        )

        analysis_results["t_pi"].push(fit_results["t_pi"])
        analysis_results["t_pi_err"].push(fit_errs["t_pi"])
        analysis_results["fit_xs"].push(fit_xs)
        analysis_results["fit_ys"].push(fit_ys)

        # We can also return custom annotations to be displayed, which can make use of
        # the analysis results.
        return [
            Annotation(
                "location",
                coordinates={self.duration: analysis_results["t_pi"]},
                data={"axis_0_error": analysis_results["t_pi_err"]},
            ),
            Annotation(
                "curve",
                {
                    self.duration: analysis_results["fit_xs"],
                    self.readout.p: analysis_results["fit_ys"],
                },
            ),
        ]


RabiFlopWithAnalysisScan = make_fragment_scan_exp(RabiFlopWithAnalysis)


class PiTimeFitSim(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("flop", RabiFlopWithAnalysis)
        self.setattr_param(
            "max_duration",
            FloatParam,
            "Maximum pulse duration",
            unit="us",
            default=1 * us,
        )
        self.setattr_param("num_points", IntParam, "Number of points", default=31)

        # With expose_analysis_results == True (the default), setattr_subscan() creates
        # results channels in this fragment that contain the analysis results from the
        # subscan (e.g. t_pi).
        setattr_subscan(
            self,
            "scan",
            self.flop,
            [(self.flop, "duration")],
            expose_analysis_results=True,
        )

    def run_once(self):
        self.scan.run(
            [
                (
                    self.flop.duration,
                    LinearGenerator(
                        0, self.max_duration.get(), self.num_points.get(), True
                    ),
                )
            ]
        )


PiTimeFitSimScan = make_fragment_scan_exp(PiTimeFitSim)
