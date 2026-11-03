# -*- coding: utf-8 -*-
"""Hour-by-hour simple Gaussian plume over a meteorological record. NOT AERMOD. No QGIS imports.
Statistics are streamed so that a full year (8784 h) never needs one field per hour in memory."""
import numpy as np

from .gauss_np import conc_field
from .met_hourly import wind_at

STATS = ("max1h", "max24h", "mean")


def run(sources, X, Y, hours, stat="max1h", months=None, min_ws=1.0, progress=None, meander=True, theta_scale=1.0):
    """hours: list from met_hourly.read_csv()['hours'] in time order. months: set of 1-12 or None.
    Returns dict(field, n_used, n_calm, classes, when_max, days) ; field in ug/m3."""
    if stat not in STATS:
        raise ValueError("stat must be one of %s" % (STATS,))
    sel = [h for h in hours if not months or h["month"] in months]
    if not sel:
        raise ValueError("No hours left after the month filter.")
    best = np.zeros_like(X, dtype=float)
    total = np.zeros_like(X, dtype=float)
    day_sum = np.zeros_like(X, dtype=float)
    day_n, day_key = 0, None
    n_calm, classes, when = 0, {}, ""
    last_year = [None]
    day_max = np.zeros_like(X, dtype=float)
    n_days = 0

    best24 = [0.0, ""]

    def close_day():
        nonlocal day_sum, day_n, n_days
        if day_n >= 18:  # a day needs at least 18 valid hours
            dm = day_sum / day_n
            m24 = float(dm.max())
            if m24 > best24[0]:
                k = day_key
                best24[:] = [m24, "%d/%d/%s 24 hr" % (k[0], k[1], last_year[0] or "")]
            np.maximum(day_max, dm, out=day_max)
            n_days += 1
        day_sum = np.zeros_like(X, dtype=float)
        day_n = 0

    for i, h in enumerate(sel):
        key = (h["month"], h["day"])
        last_year[0] = h.get("year")
        if stat == "max24h" and key != day_key:
            if day_key is not None:
                close_day()
            day_key = key
        ws = h["ws"]
        if ws < min_ws:
            n_calm += 1
            ws = min_ws
        c = np.zeros_like(X, dtype=float)
        for s in sources:
            u = wind_at(ws, h["zref"], s["height"], h["cls"])
            c += conc_field([s], X, Y, u, h["wd"], h["cls"], h["ta_c"] + 273.15, meander, theta_scale)
        classes[h["cls"]] = classes.get(h["cls"], 0) + 1
        if stat == "max1h":
            m = float(c.max())
            if m > float(best.max()):
                when = "%d/%d/%s %02d hr" % (h["month"], h["day"], h.get("year") or "", h["hour"])
            np.maximum(best, c, out=best)
        elif stat == "max24h":
            day_sum += c
            day_n += 1
        else:
            total += c
        if progress and i % 200 == 0:
            progress(100.0 * i / len(sel))
    if stat == "max24h":
        close_day()
        field = day_max
        when = best24[1]
    elif stat == "max1h":
        field = best
    else:
        field = total / len(sel)
    return {"field": field, "n_used": len(sel), "n_calm": n_calm, "classes": classes, "when_max": when, "days": n_days}
