#!/usr/bin/env python3

import numpy as np
from scipy.optimize import curve_fit
import pyqtgraph as pg
from artiq.applets.simple import TitleApplet
from PyQt5.QtCore import QTimer


def ellipse_func(t, x0, y0, a, b, theta):
    """
    Parametric equation for an ellipse centered at (x0, y0) with semi-major axis a,
    semi-minor axis b, and rotated by angle theta (in radians).
    """
    cos_t = np.cos(t)
    sin_t = np.sin(t)
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)

    x = x0 + a * cos_t * cos_theta - b * sin_t * sin_theta
    y = y0 + a * cos_t * sin_theta + b * sin_t * cos_theta
    return np.concatenate((x, y))


def extract_differential_phase_from_ellipse_params(
    params,
) -> np.ndarray:
    """
        Convert the ellipse parameters to differential phase measurement

        I'm representing my ellipses with the centre point $(x_0, y_0)$, the lengths
        of the semi-minor and semi-major axes $(a_0, b_0)$ and the tilt of the
        semi-major axis $\theta_0$. You might think that I should constrain my tilt
        to be 45 degrees, but that's only true if the contrast of both
        interferometers is equal.

        According to the Wikipedia article on ellipses, you can map from this
        representation to the one that Kasevich used in DOI:10.1364/OL.27.000951
        via:

        $$
        A = a^2 \sin^2 \theta + b^2 \cos^2 \theta
        \\
        B = 2(b^2 - a^2) \sin\theta \cos\theta
        \\
        C = a^2 \cos^2\theta + b^2 \sin^2\theta
        \\
        D = -2Ax_0 -By_0
        \\
        E = -Bx_0 -2CY_0
        \\
        F = Ax_0^2 + Bx_0y_0 Cy_0^2 -a^2b^2
        $$

        Eq 3 from [DOI:10.1364/OL.27.000951] then gives the differential phase:

        $$
        \Delta\phi = \cos^{-1} \left( \frac{-B}{2\sqrt{AC}} \right)
        $$
    """

    delta_phis = []

    a, b, x0, y0, theta0 = params

    A = a**2 * np.sin(theta0) ** 2 + b**2 * np.cos(theta0) ** 2
    B = 2 * (b**2 - a**2) * np.sin(theta0) * np.cos(theta0)
    C = a**2 * np.cos(theta0) ** 2 + b**2 * np.sin(theta0) ** 2
    D = -2 * A * x0 - B * y0
    E = -B * x0 - 2 * C * y0
    F = A * x0**2 + B * x0 * y0 + C * y0**2 - a**2 * b**2

    delta_phi = np.arccos(-B / (2 * np.sqrt(A * C)))

    return delta_phi


def fit_ellipse(x, y):
    t_data = np.linspace(0, 2 * np.pi, len(x))
    data = np.concatenate((x, y))
    initial_guess = [
        np.mean(x),  # x0
        np.mean(y),  # y0
        np.std(x),  # a (semi-major axis)
        np.std(y),  # b (semi-minor axis)
        0,  # theta (rotation angle)
    ]

    # Fit the ellipse function to the data
    try:
        params, _ = curve_fit(ellipse_func, t_data, data, p0=initial_guess)
        return params
    except RuntimeError:
        return None


class IJDPlot(pg.PlotWidget):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.length_warning)
        self.mismatch = {"X values": False}
        self.plotItem.setLabel("left", "Read Voltage (V)")
        x_label = args.x_label
        self.plotItem.setLabel("bottom", x_label)

    def data_changed(self, value, metadata, persist, mods, title):
        try:
            y = value[self.args.y]
        except KeyError:
            return
        x = value.get(self.args.x)
        if x is None:
            x = np.arange(len(y))

        if not len(y) or len(y) != len(x):
            self.mismatch["X values"] = True
        else:
            self.mismatch["X values"] = False
        if not any(self.mismatch.values()):
            self.timer.stop()
        else:
            if not self.timer.isActive():
                self.timer.start(1000)
            return

        self.clear()
        self.plot(x, y, pen=None, symbol="x")
        self.setTitle(title)

        # Fit an ellipse to the data
        ellipse_params = fit_ellipse(x, y)
        if ellipse_params is not None:
            t_fit = np.linspace(0, 2 * np.pi, 100)
            x_fit = (
                ellipse_params[0]
                + ellipse_params[2] * np.cos(t_fit) * np.cos(ellipse_params[4])
                - ellipse_params[3] * np.sin(t_fit) * np.sin(ellipse_params[4])
            )
            y_fit = (
                ellipse_params[1]
                + ellipse_params[2] * np.cos(t_fit) * np.sin(ellipse_params[4])
                + ellipse_params[3] * np.sin(t_fit) * np.cos(ellipse_params[4])
            )
            delta_phi = extract_differential_phase_from_ellipse_params(ellipse_params)
            self.plot(x_fit, y_fit, pen="r", name="Fitted Ellipse")
            # show delta_phi on the plot
            self.addItem(
                pg.TextItem(
                    f"Delta Phi: {delta_phi:.2f}",
                    color="w",
                    anchor=(0, 1),
                )
            )

            # show

    def length_warning(self):
        self.clear()
        text = "⚠️ dataset lengths mismatch:\n"
        errors = ", ".join([k for k, v in self.mismatch.items() if v])
        text = " ".join([errors, "should have the same length as Y values"])
        self.addItem(pg.TextItem(text))


def main():
    applet = TitleApplet(IJDPlot)
    applet.add_dataset("y", "Y values")
    applet.add_dataset("x", "X values")
    applet.argparser.add_argument(
        "--x_label",
        help="Label for the X axis",
    )
    applet.run()


if __name__ == "__main__":
    main()
