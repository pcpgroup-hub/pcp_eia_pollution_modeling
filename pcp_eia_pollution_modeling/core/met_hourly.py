# -*- coding: utf-8 -*-
"""Hourly meteorology from a CSV made out of an AERMET surface file (.SFC). No QGIS imports.

Columns are located from the RIGHT of each row (wind speed, wind direction, reference height, temperature, ... are the
last 10 values) because some converters drop empty fields in the middle of the row, which shifts the middle columns.
Year, month, day, hour, heat flux and friction velocity are always the first columns and are read from the left."""
import csv
import math

_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_MISSING = (-999.0, -9999.0, 999.0, 9999.0)
# Wind-profile exponents for the wind at stack height (rural, ISC-type values)
_P = {"A": 0.07, "B": 0.07, "C": 0.10, "D": 0.15, "E": 0.35, "F": 0.55}


def _num(t):
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def _month(t):
    t = (t or "").strip()
    if t[:3].lower() in _MONTHS:
        return _MONTHS[t[:3].lower()]
    v = _num(t)
    return int(v) if v else None


def stability_from_L(L):
    """Pasquill-type class from the Monin-Obukhov length (m), after Golder (1972), roughness about 0.1 m.
    Approximate: the classes only select the dispersion curves of the simple Gaussian model."""
    if L is None or abs(L) > 123:
        return "D"
    if L < 0:
        return "A" if L > -11 else ("B" if L > -26 else "C")
    return "F" if L <= 26 else "E"


def obukhov(H, ustar, Ta_c):
    """L = -rho*cp*T*u*^3 / (k*g*H), rho*cp ~ 1200 J m-3 K-1. None when the flux is missing or tiny."""
    if H is None or ustar is None or ustar <= 0 or abs(H) < 0.5:
        return None
    return -1200.0 * (Ta_c + 273.15) * ustar ** 3 / (0.4 * 9.81 * H)


def wind_at(ws, zref, h, stability):
    return ws * (max(h, zref) / zref) ** _P[stability]


def _offsets(header):
    """Position of the wind/temperature columns counted from the right end of the row (robust to dropped middle fields)."""
    names = [h.strip().lower() for h in header]
    n = len(names)

    def off(*cands, default):
        for c in cands:
            if c in names:
                return n - 1 - names.index(c)
        return default
    return dict(ws=off("wind_speed", "ws", default=9), wd=off("wind_direction", "wd", default=8),
                zref=off("reference_height_wind", default=7), ta=off("surface_temp", "temperature", default=6))


def _read_simple(rd, names):
    """Simple hourly format: Year, Month, Day, Hour, Wind_Speed, Wind_Direction, Surface_Temp, ..., Stability_Class."""
    ix = {k: names.index(k) for k in ("month", "day", "hour", "wind_speed", "wind_direction", "stability_class")}
    if "year" in names:
        ix["year"] = names.index("year")
    it = names.index("surface_temp") if "surface_temp" in names else None
    irh = names.index("relative_humidity") if "relative_humidity" in names else None
    ip = names.index("pressure") if "pressure" in names else None
    im = names.index("mixing_height") if "mixing_height" in names else None
    out, bad, missing = [], 0, 0
    for r in rd:
        if not r or not any(x.strip() for x in r):
            continue
        try:
            ws, wd = float(r[ix["wind_speed"]]), float(r[ix["wind_direction"]])
            mo, day, hr = _month(r[ix["month"]]), int(float(r[ix["day"]])), int(float(r[ix["hour"]]))
            yr = int(float(r[ix["year"]])) if "year" in ix else None
        except (ValueError, IndexError):
            bad += 1
            continue
        if hr == 0 and mo is not None and yr:
            # hour 0 closes the previous day: record it as hour 24 of that day (hour-ending convention)
            import datetime
            try:
                dd = datetime.date(yr, mo, day) - datetime.timedelta(days=1)
                mo, day, hr, yr = dd.month, dd.day, 24, dd.year
            except ValueError:
                pass
        cls = r[ix["stability_class"]].strip().upper()[:1]
        if mo is None or ws in _MISSING or wd in _MISSING or ws < 0 or not 0 <= wd <= 360 or cls not in _P:
            missing += 1
            continue
        ta = _num(r[it]) if it is not None and it < len(r) else None
        out.append(dict(year=yr, month=mo, day=day, hour=hr, ws=ws, wd=wd, zref=10.0, ta_c=25.0 if ta is None or ta in _MISSING else ta,
                        H=None, ustar=None, L=None, cls=cls,
                        rh=_num(r[irh]) if irh is not None and irh < len(r) else None,
                        pres=_num(r[ip]) if ip is not None and ip < len(r) else None,
                        mixh=_num(r[im]) if im is not None and im < len(r) else None))
    return {"hours": out, "bad_rows": bad, "missing": missing}


def read_csv(path):
    """Return dict: hours (list of dicts: month, day, hour, ws, wd, ta_c, H, ustar, L, cls) and counts."""
    out, bad, missing = [], 0, 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rd = csv.reader(fh)
        header = next(rd, None) or []
        names = [h.strip().lower() for h in header]
        if "stability_class" in names and "wind_speed" in names:
            return _read_simple(rd, names)
        o = _offsets(header)
        for r in rd:
            if not r or not any(x.strip() for x in r):
                continue
            r = [x.strip() for x in r]
            while r and r[-1] == "":
                r.pop()
            need = max(o.values()) + 1
            if len(r) < max(need, 7):
                bad += 1
                continue
            ws, wd, zref, ta = (_num(r[-1 - o[k]]) for k in ("ws", "wd", "zref", "ta"))
            mo, day, hr = _month(r[1]), _num(r[2]), _num(r[4])
            H, us = _num(r[5]), _num(r[6])
            if None in (ws, wd, mo, day, hr) or ws in _MISSING or wd in _MISSING or ws < 0 or not 0 <= wd <= 360:
                missing += 1
                continue
            ta = 25.0 if ta is None or ta in _MISSING else ta
            zref = 10.0 if not zref or zref <= 0 or zref in _MISSING else zref
            L = obukhov(H, us, ta)
            yr0 = _num(r[0])
            out.append(dict(year=int(yr0) if yr0 else None, month=mo, day=int(day), hour=int(hr), ws=ws, wd=wd, zref=zref, ta_c=ta, H=H, ustar=us, L=L,
                            cls=stability_from_L(L)))
    return {"hours": out, "bad_rows": bad, "missing": missing}
