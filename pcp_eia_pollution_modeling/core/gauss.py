# -*- coding: utf-8 -*-
"""Simple steady-state Gaussian plume for quick screening and illustration. No QGIS imports.

NOT AERMOD: one wind speed, one wind direction, one Pasquill class, open-country Briggs
sigma curves, final plume rise only, flat terrain, no building downwash. Use it to
compare scenarios quickly or to preview a map; the regulatory result comes from AERMOD.
"""
import math

_G = 9.81

# Briggs (1973) open-country sigma_y, sigma_z as functions of downwind distance x (m)
_SIGMA = {
    "A": (lambda x: 0.22 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.20 * x),
    "B": (lambda x: 0.16 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.12 * x),
    "C": (lambda x: 0.11 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.08 * x / math.sqrt(1 + 0.0002 * x)),
    "D": (lambda x: 0.08 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.06 * x / math.sqrt(1 + 0.0015 * x)),
    "E": (lambda x: 0.06 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.03 * x / (1 + 0.0003 * x)),
    "F": (lambda x: 0.04 * x / math.sqrt(1 + 0.0001 * x), lambda x: 0.016 * x / (1 + 0.0003 * x)),
}
_DTHETA_DZ = {"E": 0.02, "F": 0.035}  # K/m, stable classes


def plume_rise(vel, diam, temp_k, amb_k, u, stability):
    """Briggs final buoyant plume rise (m)."""
    if temp_k <= amb_k:
        return 0.0
    f = _G * vel * diam ** 2 / 4.0 * (temp_k - amb_k) / temp_k
    if stability in _DTHETA_DZ:
        s = _G / amb_k * _DTHETA_DZ[stability]
        return 2.6 * (f / (u * s)) ** (1.0 / 3.0)
    if f < 55:
        return 21.425 * f ** 0.75 / u
    return 38.71 * f ** 0.6 / u


def sigma_y(x, stability="D"):
    """Lateral plume spread (m) at downwind distance x (m)."""
    return _SIGMA[stability][0](x)


def grid_too_coarse(n_points, area_m2, stability="D", x_ref=500.0):
    """True when the mean receptor spacing is wider than half the plume width at x_ref:
    contours then break into beads. Returns (flag, spacing_m, half_plume_width_m)."""
    spacing = (area_m2 / max(n_points, 1)) ** 0.5
    half = sigma_y(x_ref, stability) / 2.0
    return spacing > half, spacing, half


def ground_conc(src, rx, ry, u, wind_from_deg, stability="D", amb_k=298.0):
    """Ground-level concentration (ug/m3) at (rx, ry) from one source dict
    (x, y, emis g/s, height m, temp K, vel m/s, diam m). Wind blows FROM wind_from_deg."""
    if u <= 0:
        raise ValueError("wind speed must be positive")
    if stability not in _SIGMA:
        raise ValueError("stability must be one of A-F")
    toward = math.radians((wind_from_deg + 180.0) % 360.0)
    dx, dy = rx - src["x"], ry - src["y"]
    xd = dx * math.sin(toward) + dy * math.cos(toward)     # downwind
    yc = dx * math.cos(toward) - dy * math.sin(toward)     # crosswind
    if xd < 1.0:
        return 0.0
    sy, sz = _SIGMA[stability][0](xd), _SIGMA[stability][1](xd)
    h = src["height"] + plume_rise(src["vel"], src["diam"], src["temp"], amb_k, u, stability)
    c = src["emis"] / (math.pi * u * sy * sz) * math.exp(-yc * yc / (2 * sy * sy)) * math.exp(-h * h / (2 * sz * sz))
    return c * 1e6


def field(sources, receptors, u, wind_from_deg, stability="D", amb_k=298.0):
    """Sum over sources for each (x, y) receptor; returns list of ug/m3."""
    return [sum(ground_conc(s, x, y, u, wind_from_deg, stability, amb_k) for s in sources) for x, y in receptors]


def parse_rose(text):
    """16 wind-rose frequencies (wind FROM N, NNE, ... NNW; per cent or fractions). Returns fractions per sector."""
    import re
    vals = [float(t) for t in re.split(r"[\s;,]+", (text or "").strip().replace(",", " ")) if t]
    if len(vals) != 16 or any(v < 0 for v in vals) or sum(vals) <= 0:
        raise ValueError("wind rose needs 16 non-negative numbers (from N clockwise, 22.5 deg steps)")
    tot = sum(vals)
    return [v / 100.0 for v in vals] if tot > 1.5 else vals


def _rose_freq(rose, from_deg):
    """Per-sector frequency for wind coming from from_deg, linearly interpolated between sector centres."""
    pos = (from_deg % 360.0) / 22.5
    i = int(math.floor(pos)) % 16
    t = pos - math.floor(pos)
    return rose[i] * (1 - t) + rose[(i + 1) % 16] * t


def sector_conc(src, rx, ry, u, rose, stability="D", amb_k=298.0):
    """Long-term (sector-averaged) ground-level concentration (ug/m3) from one source for a 16-sector wind rose,
    one wind speed and one stability class. Smooth, whole-domain field like a year of hourly data would give."""
    if u <= 0:
        raise ValueError("wind speed must be positive")
    if stability not in _SIGMA:
        raise ValueError("stability must be one of A-F")
    dx, dy = rx - src["x"], ry - src["y"]
    x = math.hypot(dx, dy)
    if x < 30.0:
        return 0.0
    bearing = math.degrees(math.atan2(dx, dy)) % 360.0     # direction the plume travels towards
    f = _rose_freq(rose, bearing + 180.0)
    if f <= 0:
        return 0.0
    sz = _SIGMA[stability][1](x)
    h = src["height"] + plume_rise(src["vel"], src["diam"], src["temp"], amb_k, u, stability)
    dtheta = 2.0 * math.pi / 16.0
    c = math.sqrt(2.0 / math.pi) * src["emis"] * f / (sz * u * x * dtheta) * math.exp(-h * h / (2 * sz * sz))
    return c * 1e6
