"""Small numpy-only fit helpers shared by the clock calibrations.

Kept scipy-free so they import cleanly in the ARTIQ host environment and are
trivially unit-testable off-rig.
"""

import numpy as np


def fit_peak_x(xs, ys):
    """Sub-grid x-position of the maximum of a peaked/first-rising curve.

    A parabola through the sampled maximum and its two neighbours locates the
    vertex to sub-grid resolution (Gaussian-line centre / Rabi first-max time),
    falling back to the raw argmax at the edges or on a degenerate fit. Non-finite
    y-values (e.g. excitation from a zero-atom shot) are dropped first.

    Returns None if there is no finite sample.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)

    finite = np.isfinite(ys)
    xs, ys = xs[finite], ys[finite]
    if xs.size == 0:
        return None
    if xs.size < 3:
        return float(xs[int(np.argmax(ys))])

    i = int(np.argmax(ys))
    if i == 0 or i == xs.size - 1:
        return float(xs[i])

    x0, x1, x2 = xs[i - 1], xs[i], xs[i + 1]
    y0, y1, y2 = ys[i - 1], ys[i], ys[i + 1]
    denom = (x0 - x1) * (x0 - x2) * (x1 - x2)
    if denom == 0:
        return float(x1)
    a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denom
    b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denom
    if a >= 0:  # not a maximum
        return float(x1)
    vertex = -b / (2 * a)
    if vertex < x0 or vertex > x2:  # guard against extrapolation
        return float(x1)
    return float(vertex)
