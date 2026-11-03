# -*- coding: utf-8 -*-
"""Concentration class levels and Vietnamese number formatting (pure Python, no QGIS)."""

DEFAULT_FRACTIONS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5)


def levels_from_limit(limit, fractions=DEFAULT_FRACTIONS):
    """Class levels as fractions of an expert-supplied limit (e.g. a QCVN value). The plugin ships no limit values."""
    limit = float(limit)
    if limit <= 0:
        raise ValueError("limit must be positive")
    fr = sorted(set(float(f) for f in fractions))
    if not fr or fr[0] <= 0:
        raise ValueError("fractions must be positive")
    return [round(limit * f, 6) for f in fr]


def fmt_vi(value, digits=None):
    """1234.5 -> '1234,5' (comma decimal, as in Vietnamese reports). digits=None keeps up to 4 significant decimals."""
    s = ("%.*f" % (digits, value)) if digits is not None else ("%.4f" % value).rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


_NICE = (1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9)


def _nice(v):
    """Nearest 'round' value (1, 1.5, 2, 3 ... 9 x 10^k) on a log scale."""
    import math
    if v <= 0:
        return v
    k = math.floor(math.log10(v))
    best = None
    for m in _NICE + (10,):
        cand = m * 10.0 ** k
        d = abs(math.log(cand) - math.log(v))
        if best is None or d < best[0]:
            best = (d, cand)
    return float("%.6g" % best[1])


def report_levels(vmin, vmax, n_classes=10):
    """Class edges the way AERMOD-type EIA plots look: ~10 classes between the data minimum and maximum,
    edges are round numbers spaced roughly geometrically (dense at low values, wide at the top).
    Returns the interior edges only (n_classes - 1 values, fewer if rounding merges some)."""
    import math
    if vmax <= 0 or vmax <= vmin:
        raise ValueError("need 0 <= min < max")
    lo = max(vmin, vmax * 1e-3)
    out = []
    for i in range(1, n_classes):
        t = lo * (vmax / lo) ** (i / float(n_classes))
        v = _nice(t)
        if v >= vmax:
            continue
        if not out or v > out[-1]:
            out.append(v)
    return out
