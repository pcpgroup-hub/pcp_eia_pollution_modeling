# -*- coding: utf-8 -*-
"""Vectorised simple Gaussian plume (numpy) and the '1st-high envelope' used to mimic the look of an AERMOD
'highest 1-hour value over the year' plot. NOT AERMOD: a synthetic set of meteorological conditions
(wind directions x speeds x stability classes) stands in for the hourly meteorology.
No QGIS imports."""
import math

import numpy as np

from .gauss import plume_rise

_SIG = {
    "A": (lambda x: 0.22 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.20 * x),
    "B": (lambda x: 0.16 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.12 * x),
    "C": (lambda x: 0.11 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.08 * x / np.sqrt(1 + 0.0002 * x)),
    "D": (lambda x: 0.08 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.06 * x / np.sqrt(1 + 0.0015 * x)),
    "E": (lambda x: 0.06 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.03 * x / (1 + 0.0003 * x)),
    "F": (lambda x: 0.04 * x / np.sqrt(1 + 0.0001 * x), lambda x: 0.016 * x / (1 + 0.0003 * x)),
}


# One-hour wind-direction fluctuation sigma-theta (deg) by class (EPA-type values): meander spreads a 1-h mean plume sideways
SIGMA_THETA = {"A": 22.5, "B": 17.5, "C": 12.5, "D": 7.5, "E": 5.0, "F": 3.75}


def conc_field(sources, X, Y, u, from_deg, stability="D", amb_k=298.0, meander=False, theta_scale=1.0):
    """Ground-level concentration (ug/m3) at arrays X, Y for one wind condition, summed over sources."""
    if u <= 0:
        raise ValueError("wind speed must be positive")
    if stability not in _SIG:
        raise ValueError("stability must be one of A-F")
    toward = math.radians((from_deg + 180.0) % 360.0)
    st, ct = math.sin(toward), math.cos(toward)
    total = np.zeros_like(X, dtype=float)
    for s in sources:
        dx, dy = X - s["x"], Y - s["y"]
        xd = dx * st + dy * ct
        yc = dx * ct - dy * st
        ok = xd >= 1.0
        xs = np.where(ok, xd, 1.0)
        sy, sz = _SIG[stability][0](xs), _SIG[stability][1](xs)
        if meander:  # add the lateral spread of the wind-direction fluctuation over the hour
            sy = np.sqrt(sy * sy + (xs * math.radians(SIGMA_THETA[stability] * theta_scale)) ** 2)
        h = s["height"] + plume_rise(s["vel"], s["diam"], s["temp"], amb_k, u, stability)
        c = s["emis"] / (math.pi * u * sy * sz) * np.exp(-yc * yc / (2 * sy * sy)) * np.exp(-h * h / (2 * sz * sz))
        total += np.where(ok, c, 0.0) * 1e6
    return total


def first_high(sources, X, Y, dirs, speeds, stabs, amb_k=298.0, factor=1.0):
    """Highest value over all (direction, speed, stability) conditions at each receptor, times `factor`
    (1.0 for 1 h; a persistence factor, e.g. 0.4 as in SCREEN3, may be given by the expert for 24 h)."""
    best = np.zeros_like(X, dtype=float)
    for st in stabs:
        for u in speeds:
            for d in dirs:
                np.maximum(best, conc_field(sources, X, Y, u, d, st, amb_k), out=best)
    return best * factor
