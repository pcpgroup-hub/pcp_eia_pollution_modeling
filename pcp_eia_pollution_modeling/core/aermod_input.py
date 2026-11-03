# -*- coding: utf-8 -*-
"""Build an AERMOD control file (.inp) from plain data. No QGIS imports.

Keywords follow the AERMOD User's Guide (CO, SO, RE, ME, OU pathways). Everything the
expert must decide (meteorology files, station ids, pollutant, averaging, dispersion
options) is an explicit argument; nothing is invented. Coordinates must already be in
a projected CRS in metres (UTM).
"""
import re

_ID = re.compile(r"^[A-Za-z0-9_]{1,8}$")


def _need_id(value, what):
    if not _ID.match(value or ""):
        raise ValueError("%s %r must be 1-8 letters/digits/underscore (AERMOD limit)" % (what, value))
    return value


def _num(v):
    """Plain decimal, never exponent form, no precision loss for UTM coordinates (7 digits)."""
    t = ("%.3f" % float(v)).rstrip("0").rstrip(".")
    return t if t not in ("", "-0") else "0"


def build_inp(title, pollutant, sources, receptors, surf_file, prof_file,
              surf_station, surf_year, upper_station, upper_year, prof_base_elev,
              avg_times=("1", "24", "PERIOD"), dfault=True, plot_name="plot.plt",
              urban=None):
    """Return the text of an AERMOD input file.

    sources: list of dicts id, x, y, z, emis (g/s), height (m), temp (K), vel (m/s), diam (m).
    receptors: list of (x, y) or (x, y, zelev).
    avg_times: hours as strings, or 'PERIOD'.
    """
    if not sources:
        raise ValueError("at least one source is required")
    if not receptors:
        raise ValueError("at least one receptor is required")
    seen = set()
    lines = ["CO STARTING", "   TITLEONE  " + title[:60].replace("\n", " "),
             "   MODELOPT  " + ("DFAULT " if dfault else "") + "CONC",
             "   AVERTIME  " + " ".join(avg_times),
             "   POLLUTID  " + _need_id(pollutant, "pollutant"),
             "   RUNORNOT  RUN", "   ERRORFIL", "CO FINISHED", "SO STARTING",
             "   ELEVUNIT  METERS"]
    for s in sources:
        sid = _need_id(s["id"], "source id")
        if sid in seen:
            raise ValueError("duplicate source id %s" % sid)
        seen.add(sid)
        for k in ("x", "y", "emis", "height", "temp", "vel", "diam"):
            if s.get(k) is None:
                raise ValueError("source %s: missing %s" % (sid, k))
        lines.append("   LOCATION  %s POINT %s %s %s" % (sid, _num(s["x"]), _num(s["y"]), _num(s.get("z") or 0)))
        lines.append("   SRCPARAM  %s %s %s %s %s %s" % (sid, _num(s["emis"]), _num(s["height"]),
                                                       _num(s["temp"]), _num(s["vel"]), _num(s["diam"])))
    if urban:
        lines.append("   URBANSRC  ALL")
    lines += ["   SRCGROUP  ALL", "SO FINISHED", "RE STARTING"]
    for r in receptors:
        z = r[2] if len(r) > 2 else 0
        lines.append("   DISCCART  %s %s %s" % (_num(r[0]), _num(r[1]), _num(z)))
    lines += ["RE FINISHED", "ME STARTING", "   SURFFILE  " + surf_file, "   PROFFILE  " + prof_file,
              "   SURFDATA  %s %s" % (surf_station, surf_year),
              "   UAIRDATA  %s %s" % (upper_station, upper_year),
              "   PROFBASE  %s METERS" % _num(prof_base_elev), "ME FINISHED", "OU STARTING"]
    first = True
    if any(a.upper() != "PERIOD" for a in avg_times):
        # AERMOD only accepts a ranked-value PLOTFILE when the same rank is also requested in a table
        lines.append("   RECTABLE  ALLAVE FIRST")
    for a in avg_times:
        if a.upper() == "PERIOD":
            lines.append("   PLOTFILE  PERIOD ALL %s" % plot_name.replace(".plt", "_period.plt"))
        else:
            lines.append("   PLOTFILE  %s ALL FIRST %s" % (a, plot_name.replace(".plt", "_%sh.plt" % a)))
        first = False
    lines += ["OU FINISHED", ""]
    return "\n".join(lines)


def check_inp_lengths(text, limit=132):
    """Names of lines over AERMOD's 132-character limit (1-based numbers)."""
    return [i + 1 for i, l in enumerate(text.splitlines()) if len(l) > limit]
