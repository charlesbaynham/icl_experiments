from functools import partial
from typing import Iterable, Optional
import numpy as np
from scipy.optimize import curve_fit
from scipy.constants import k as kB
from scipy.constants import atomic_mass
from repository.lib.constants import USE_SR87
from ndscan.experiment.default_analysis import CustomAnalysis
from ndscan.experiment.result_channels import ResultChannel
from ndscan.experiment.parameters import ParamHandle

# Define the mass of the atom
mass = atomic_mass * (87 if USE_SR87 else 88)

psf0 = 1
sigma00 = 1
T0 = 1e-6


# Define the expansion model function
def expansion_model(t: float, sigma0: float, T: float, psf: float):
    return np.sqrt(sigma0**2 + (kB * T / mass) * t**2 + psf**2)


def get_custom_analysis(
    x_param_handle: ParamHandle,
    y_param_handle: ParamHandle,
    analysis_results: dict[str, ResultChannel],
):

    def analyse_fn(
        axis_values: dict[ParamHandle, list],
        result_values: dict[ParamHandle, list],
        analysis_results: dict[str, ResultChannel],
        x_param: Optional[ParamHandle] = None,
        y_result: Optional[ParamHandle] = None,
    ):
        t = axis_values[x_param]
        sigma = result_values[y_result]
        popt, t_fit, sigma_fit = fit_expansion(t, sigma)
        # analysis_results["sigma0"].push(popt[0])
        analysis_results["T"].push(popt[1])
        # analysis_results["psf"].push(popt[2])
        analysis_results["fit_xs"].push(t_fit)
        analysis_results["fit_ys"].push(sigma_fit)
        return []

    fn = partial(analyse_fn, x_param=x_param_handle, y_result=y_param_handle)

    return [CustomAnalysis([x_param_handle], fn, analysis_results)]


def fit_expansion(
    t: Iterable[float],
    sigma: Iterable[float],
    p0: Optional[list] = None,
    evaluate_fn: bool = True,
    n: int = 100,
):
    if p0 is None:
        p0 = [sigma00, T0, psf0]
    popt, pcov = curve_fit(expansion_model, t, sigma, p0=p0)

    if evaluate_fn:
        t_fit = np.linspace(t[0], t[-1], n)
        sigma_fit = expansion_model(t_fit, *popt)
    else:
        t_fit = None
        sigma_fit = None

    return popt, t_fit, sigma_fit
