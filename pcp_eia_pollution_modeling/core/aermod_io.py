# -*- coding: utf-8 -*-
"""AERMOD control-file checks and PLOTFILE reading. No QGIS imports.

PLOTFILE layout (per the AERMOD User's Guide): comment lines start with '*', then
whitespace separated columns X, Y, CONC, ZELEV, ZHILL, ZFLAG, AVE, GRP, ... ; this
reader takes X, Y, CONC and, when present, AVE and GRP. Confirm against a real run
(see docs/TESTING_vi.md).
"""
import re

_MODELOPT = re.compile(r"^\s*(?:CO\s+)?MODELOPT\b(.*)$", re.IGNORECASE)


def uses_dfault(inp_text):
    """True if a non-comment MODELOPT line contains DFAULT (regulatory defaults)."""
    for line in inp_text.splitlines():
        if line.lstrip().startswith("**"):
            continue
        m = _MODELOPT.match(line)
        if m and re.search(r"\bDFAULT\b", m.group(1), re.IGNORECASE):
            return True
    return False


def read_plotfile(path):
    """Return list of dicts {x, y, conc, ave, grp}."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip() or line.lstrip().startswith("*"):
                continue
            t = line.split()
            try:
                x, y, c = float(t[0]), float(t[1]), float(t[2])
            except (ValueError, IndexError):
                continue
            rows.append({"x": x, "y": y, "conc": c,
                         "ave": t[6] if len(t) > 6 else "", "grp": t[7] if len(t) > 7 else ""})
    return rows


def run_failed(out_text):
    """EPA's test batch flags failed runs by the string 'Un-successfully'."""
    return "Un-successfully" in out_text


def referenced_files(inp_text, base_dir):
    """Absolute paths of met and include files named in an AERMOD control file."""
    import os

    found = []
    for line in inp_text.splitlines():
        if line.lstrip().startswith("**"):
            continue
        m = re.match(r"^\s*(?:ME\s+)?(SURFFILE|PROFFILE)\s+(\"[^\"]+\"|'[^']+'|\S+)", line, re.IGNORECASE)
        if not m:
            m = re.match(r"^\s*(?:\w\w\s+)?(INCLUDED)\s+(\"[^\"]+\"|'[^']+'|\S+)", line, re.IGNORECASE)
        if m:
            name = m.group(2).strip("\"'")
            found.append(name if os.path.isabs(name) else os.path.join(base_dir, name))
    return found
