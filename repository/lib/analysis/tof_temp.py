from functools import partial
from typing import Iterable
from typing import Optional

import numpy as np
from ndscan.experiment.default_analysis import CustomAnalysis
from ndscan.experiment.parameters import ParamHandle
from ndscan.experiment.result_channels import ResultChannel
from scipy.constants import atomic_mass
from scipy.constants import k as kB
from scipy.optimize import curve_fit

from repository.lib.constants import ANDOR_CAMERA_FACTS
from repository.lib.constants import USE_SR87

# Define the mass of the atom
mass = atomic_mass * (87 if USE_SR87 else 88)

psf0 = 1
sigma00 = 1
T0 = 1e-6
pixel_size = ANDOR_CAMERA_FACTS["pixel_size"]  # meters


# Define the expansion model function
def expansion_model(t: float, sigma0: float, T: float):
    return np.sqrt(sigma0**2 + (kB * T / mass) * t**2)


def get_custom_analysis(
    x_param_handle: ParamHandle,
    y_param_handle: ParamHandle,
    analysis_results_names: dict[str, str],
    analysis_results: dict[str, ResultChannel],
):
    def analyse_fn(
        axis_values: dict[ParamHandle, list],
        result_values: dict[ParamHandle, list],
        analysis_results: dict[str, ResultChannel],
        x_param: Optional[ParamHandle] = None,
        y_result: Optional[ParamHandle] = None,
        analysis_results_names: Optional[dict[str, str]] = None,
    ):
        if analysis_results_names is None:
            analysis_results_names = {"T": "T", "fit_xs": "fit_xs", "fit_ys": "fit_ys"}
        t = axis_values[x_param]
        sigma = [i * pixel_size for i in result_values[y_result]]
        popt, t_fit, sigma_fit = fit_expansion(t, sigma)
        # analysis_results["sigma0"].push(popt[0])
        analysis_results[analysis_results_names["T"]].push(popt[1])
        # analysis_results["psf"].push(popt[2])
        analysis_results[analysis_results_names["fit_xs"]].push(t_fit)
        analysis_results[analysis_results_names["fit_ys"]].push(sigma_fit)
        return []

    fn = partial(
        analyse_fn,
        x_param=x_param_handle,
        y_result=y_param_handle,
        analysis_results_names=analysis_results_names,
    )

    return [CustomAnalysis([x_param_handle], fn, analysis_results)]


def fit_expansion(
    t: Iterable[float],
    sigma: Iterable[float],
    p0: Optional[list] = None,
    evaluate_fn: bool = True,
    n: int = 100,
):
    if p0 is None:
        p0 = [sigma00, T0]

    bounds_sigma0 = (0, np.inf)
    bounds_T = (0, 1)
    bounds = list(zip(*[bounds_sigma0, bounds_T]))
    popt, pcov = curve_fit(expansion_model, t, sigma, p0=p0, bounds=bounds)

    if evaluate_fn:
        t_fit = np.linspace(t[0], t[-1], n)
        sigma_fit = expansion_model(t_fit, *popt)
    else:
        t_fit = None
        sigma_fit = None

    return popt, t_fit, sigma_fit


if __name__ == "__main__":
    # Simulated data: expansion times (s) and measured cloud widths (m)
    time_data = np.array([0, 0.01, 0.02, 0.03, 0.04, 0.05])  # seconds
    sigma_data = np.array([0.1, 0.15, 0.22, 0.28, 0.35, 0.42])  # meters
    sigma_err = np.full_like(sigma_data, 0.02)  # Error estimate in width (m)

    # Initial guesses for fitting
    mass_guess = 1.44e-25  # Example atomic mass (Rb-87 in kg)
    temp_guess = 50e-6  # Initial temperature guess in K
    sigma0_guess = 0.1  # Initial cloud width in meters
    psf_guess = 0.01  # Estimated point spread function width in meters

    # Perform the curve fit
    popt, t_fit, sigma_fit = fit_expansion(time_data, sigma_data)

    sigma0_fit, temp_fit = popt

    print(f"sigma0_fit: {sigma0_fit}")
    print(f"temp_fit: {temp_fit}")

    # Plot results
    plt.plot(time_data, sigma_data, "o", label="Data")
    t_fit = np.linspace(0, max(time_data), 100)
    plt.plot(t_fit, sigma_fit, label="Fit", linestyle="--")
    plt.xlabel("Time (s)")
    plt.ylabel("Cloud Width (m)")
    plt.legend()
    plt.title("Ballistic Expansion of Atomic Cloud")
    plt.show()
