# -*- coding: utf-8 -*-
"""US EPA AQI class edges from an editable data file (no QGIS imports).
The AQI is defined for ambient concentrations; applied to a modelled project contribution it is only a way of
colouring the map, and the legend says so."""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "epa_aqi_breakpoints.json")


def load(path=None):
    with open(path or _PATH, encoding="utf-8") as fh:
        return json.load(fh)


def keys(data=None):
    return list((data or load())["pollutants"].keys())


def to_ugm3(value, unit, mw, molar_volume=24.45):
    """ppb or ppm to ug/m3 at 25 degC, 1 atm (EPA reference conditions)."""
    if unit == "ug/m3":
        return float(value)
    ppb = float(value) * (1000.0 if unit == "ppm" else 1.0)
    return ppb * mw / molar_volume


def classes(key, data=None):
    """Return dict: levels (ug/m3, class edges between categories), colors, names (vi), label, source, warn."""
    data = data or load()
    p = data["pollutants"][key]
    mv = data.get("molar_volume_L_per_mol", 24.45)
    edges = []
    for hi in p["upper"]:
        # edge halfway to the next reported value (the EPA ranges are truncated: 9.0 | 9.1 -> 9.05)
        edges.append(round(to_ugm3(hi + p["step"] / 2.0, p["unit"], p["mw"], mv), 4))
    cats = data["categories"]
    return {"levels": edges, "colors": [c["color"] for c in cats], "names": [c["vi"] for c in cats],
            "label": p["label"], "source": data["source"], "warn": p.get("warn", ""), "key": key}
