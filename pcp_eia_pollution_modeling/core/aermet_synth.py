# -*- coding: utf-8 -*-
"""TEST-ONLY AERMET-style surface (.SFC) and profile (.PFL) files made from a simple hourly CSV (wind, temperature,
stability class). The boundary-layer parameters are ASSUMED from the stability class, not computed by AERMET from
observations. Use it to try the AERMOD workflow; results are not valid for a dossier. No QGIS imports."""
import calendar
import math

# Assumed Monin-Obukhov length (m) per class, z0 = 0.1 m style rural surface
_L = {"A": -8.0, "B": -18.0, "C": -60.0, "D": None, "E": 60.0, "F": 15.0}
_USTAR_FACTOR = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 0.8, "F": 0.6}
_R, _CP, _K, _G = 1.2, 1004.0, 0.4, 9.81


def boundary_layer(h, z0=0.1, bowen=1.0, albedo=0.2, zref=10.0):
    """Assumed surface parameters for one hour dict (needs ws, ta_c, cls; optional mixh)."""
    ws = max(h["ws"], 0.3)
    ta = h["ta_c"] + 273.15
    us = _K * ws / math.log(zref / z0) * _USTAR_FACTOR[h["cls"]]
    us = max(us, 0.05)
    L = _L[h["cls"]]
    if L is None:                      # neutral
        H, wstar, zic = 0.0, -9.0, -999.0
        zim = 2300.0 * us ** 1.5
    elif L < 0:                        # convective
        H = -_R * _CP * ta * us ** 3 / (_K * _G * L)
        zic = float(h.get("mixh") or 1000.0)
        zic = max(zic, 100.0)
        wstar = (_G / ta * H / (_R * _CP) * zic) ** (1.0 / 3.0)
        zim = 2300.0 * us ** 1.5
    else:                              # stable
        H = -_R * _CP * ta * us ** 3 / (_K * _G * L)
        wstar, zic = -9.0, -999.0
        zim = max(2300.0 * us ** 1.5, 20.0)
    return dict(H=H, ustar=us, wstar=wstar, vptg=0.005, zic=zic, zim=zim, L=L if L else 99999.0, z0=z0, bowen=bowen,
                albedo=albedo)


def _doy(year, month, day):
    return sum(calendar.monthrange(year, m)[1] for m in range(1, month)) + day


def make_files(hours, year, lat, lon, station="99999", zref=10.0, ztemp=10.0, z0=0.1):
    """Return (sfc_text, pfl_text). hours: list of dicts with month, day, hour (1-24), ws, wd, ta_c, cls, rh, pres, mixh."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    head = "%8.3f%s %9.3f%s   UA_ID: %-8s  SF_ID: %-8s  OS_ID:           VERSION: 24142   TEST-ONLY ASSUMED PARAMETERS" % (
        abs(lat), ns, abs(lon), ew, station, station)
    sfc = [head]
    pfl = []
    yy = year % 100
    for h in hours:
        bl = boundary_layer(h, z0)
        jd = _doy(year, h["month"], h["day"])
        sfc.append(" %02d %02d %02d %3d %02d %8.1f %7.3f %7.3f %7.3f %6.0f %6.0f %9.1f %7.3f %6.2f %6.2f %7.2f %6.0f %6.1f %7.1f %6.1f %3d %6.2f %5.0f %7.0f %4d %s" % (
            yy, h["month"], h["day"], jd, h["hour"], bl["H"], bl["ustar"], bl["wstar"], bl["vptg"], bl["zic"], bl["zim"],
            bl["L"], bl["z0"], bl["bowen"], bl["albedo"], max(h["ws"], 0.3), h["wd"], zref, h["ta_c"] + 273.15, ztemp,
            0, 0.0, h.get("rh") or 80.0, h.get("pres") or 1010.0, 5, "NAD-SUB"))
        pfl.append(" %02d %02d %02d %02d %6.1f %d %5.0f %7.2f %7.1f %6.1f %7.2f" % (
            yy, h["month"], h["day"], h["hour"], zref, 1, h["wd"], max(h["ws"], 0.3), h["ta_c"], -99.0, -99.0))
    return "\n".join(sfc) + "\n", "\n".join(pfl) + "\n"
