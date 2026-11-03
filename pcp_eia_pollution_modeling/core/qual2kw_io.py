# -*- coding: utf-8 -*-
"""Bridge helpers for the official QUAL2Kw workbook (pure Python, no QGIS).

The plugin does not contain or run QUAL2Kw. It (a) prepares tables laid out like the
'Reach' and 'Point Sources' sheets so the expert can paste them into the official workbook,
and (b) reads the 'WQ Output' sheet of a workbook the expert has run.
Distances follow the QUAL2Kw convention: km measured UPSTREAM from the downstream end (headwater = largest km).
"""
import csv
import math
import re
import zipfile
import xml.etree.ElementTree as ET  # nosec B405 - every parse below is preceded by the _no_dtd() guard

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Fields accepted on the point-source layer -> (column title, unit) in QUAL2Kw order
SOURCE_FIELDS = (
    ("q_out", "Point abstraction", "m3/s"), ("q_in", "Point inflow", "m3/s"),
    ("temp", "Temperature", "C"), ("cond", "Conductivity", "uS/cm 25C"),
    ("iss", "Inorganic suspended solids", "mgD/L"), ("do", "Dissolved oxygen", "mg/L"),
    ("cbods", "Slow CBOD", "mgO2/L"), ("cbodf", "Fast CBOD", "mgO2/L"),
    ("orgn", "Organic N", "ugN/L"), ("nh4", "Ammonia N", "ugN/L"), ("no3", "Nitrate + nitrite N", "ugN/L"),
    ("orgp", "Organic P", "ugP/L"), ("srp", "Inorganic P", "ugP/L"),
)


def dms(value):
    """Decimal degrees -> (deg, min, sec) of the absolute value."""
    a = abs(float(value))
    d = int(a)
    m = int((a - d) * 60)
    s = round((a - d - m / 60.0) * 3600, 2)
    if s >= 60:
        s -= 60
        m += 1
    if m >= 60:
        m -= 60
        d += 1
    return d, m, s


def polyline_length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def point_at(pts, s):
    """Point at chainage s along a polyline of (x, y); clamped to the ends."""
    if s <= 0:
        return pts[0]
    for a, b in zip(pts, pts[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg > 0 and s <= seg:
            t = s / seg
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        s -= seg
    return pts[-1]


def sub_line(pts, s0, s1):
    """Vertices of the polyline between chainages s0 and s1."""
    out = [point_at(pts, s0)]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if s0 < acc < s1:
            out.append(b)
    out.append(point_at(pts, s1))
    return out


def reach_breaks(total_m, reach_km):
    """Chainages (m from the headwater) of reach ends. The last reach absorbs a remainder under half a reach."""
    step = float(reach_km) * 1000.0
    if step <= 0 or total_m <= 0:
        raise ValueError("reach length and river length must be positive")
    n = max(1, int(round(total_m / step)))
    return [total_m * i / n for i in range(1, n + 1)]


def build_reach_rows(pts, to_lonlat, reach_km, elev_up=None, elev_down=None, label_first="Headwater"):
    """Reach table rows. pts: river vertices headwater->mouth in a metric CRS; to_lonlat(x, y)->(lon, lat)."""
    total = polyline_length(pts)
    ends = reach_breaks(total, reach_km)
    lon, lat = to_lonlat(*pts[0])
    rows = [{"label": label_first, "reach": 0, "length_km": "", "lat": lat, "lon": lon,
             "down_km": total / 1000.0, "elev_up": "", "elev_down": elev_up if elev_up is not None else ""}]
    prev = 0.0
    for i, e in enumerate(ends, 1):
        x, y = point_at(pts, e)
        lon, lat = to_lonlat(x, y)
        frac = e / total
        ed = ""
        if elev_up is not None and elev_down is not None:
            ed = round(elev_up + (elev_down - elev_up) * frac, 3)
        eu = rows[-1]["elev_down"]
        rows.append({"label": "", "reach": i, "length_km": round((e - prev) / 1000.0, 4), "lat": lat, "lon": lon,
                     "down_km": round((total - e) / 1000.0, 4), "elev_up": eu, "elev_down": ed})
        prev = e
    return rows


def write_reach_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Reach label", "Reach number", "Reach length (km)", "Downstream latitude (deg, + north)",
                    "Downstream longitude (deg, + west)", "Downstream location (km)",
                    "Elevation upstream (m)", "Elevation downstream (m)",
                    "Lat deg", "Lat min", "Lat sec", "Lon deg", "Lon min", "Lon sec"])
        for r in rows:
            la, lo = dms(r["lat"]), dms(r["lon"])
            # QUAL2Kw wants longitude positive WEST; keep the sign convention explicit in the header
            w.writerow([r["label"], r["reach"], r["length_km"], round(r["lat"], 6), round(-r["lon"], 6),
                        round(r["down_km"], 4), r["elev_up"], r["elev_down"], la[0], la[1], la[2], lo[0], lo[1], lo[2]])


def write_sources_csv(path, rows):
    """rows: dicts with name, km and any SOURCE_FIELDS keys."""
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Name", "Location (km)"] + ["%s (%s)" % (t, u) for _, t, u in SOURCE_FIELDS])
        for r in rows:
            w.writerow([r.get("name", ""), round(r["km"], 4)] + [r.get(k, "") for k, _, _ in SOURCE_FIELDS])


# ---------------- reading results ----------------

def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _no_dtd(head):
    """Refuse XML that declares a DTD or entities (the basis of XML-expansion attacks).
    A genuine Excel workbook never contains either."""
    low = head.lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise ValueError("The workbook XML contains a DTD or entity declaration; refusing to read it")


def _xml_root(z, name):
    data = z.read(name)
    _no_dtd(data)
    return ET.fromstring(data)  # nosec B314 - DTD/entities rejected above


def _sheet_path(z, name):
    wb = _xml_root(z, "xl/workbook.xml")
    rels = {r.get("Id"): r.get("Target") for r in _xml_root(z, "xl/_rels/workbook.xml.rels")}
    for s in wb.find(_M + "sheets"):
        if s.get("name") == name:
            t = rels[s.get(_R + "id")].lstrip("/")
            return t if t.startswith("xl/") else "xl/" + t
    raise ValueError("Sheet '%s' not found in the workbook" % name)


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_wq_output_xlsx(path, sheet="WQ Output", max_rows=5000):
    """Read the constituent summary of a run workbook. Returns (headers, rows); row = {'label','km','values':{header:float}}.
    Only the named sheet is parsed, so very large run workbooks are fine."""
    z = zipfile.ZipFile(path)
    sp = _sheet_path(z, sheet)
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in _xml_root(z, "xl/sharedStrings.xml").iter(_M + "si"):
            strings.append("".join(t.text or "" for t in si.iter(_M + "t")))
    table = []
    with z.open(sp) as head_f:
        _no_dtd(head_f.read(65536))  # a DTD can only appear at the start of the document
    for _, el in ET.iterparse(z.open(sp), events=("end",)):  # nosec B314 - DTD rejected above
        if el.tag == _M + "row":
            cells = {}
            for c in el:
                v = c.find(_M + "v")
                if v is None or v.text is None:
                    continue
                cells[_col_index(c.get("r"))] = strings[int(v.text)] if c.get("t") == "s" else v.text
            if cells:
                table.append(cells)
            el.clear()
            if len(table) > max_rows:
                break
    return _parse_table(table)


def read_wq_output_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        table = [{i: v for i, v in enumerate(r) if v != ""} for r in csv.reader(fh)]
    return _parse_table([t for t in table if t])


def _parse_table(table):
    hi = None
    for i, t in enumerate(table):
        if str(t.get(0, "")).strip().lower() == "reach" and "distance" in str(t.get(1, "")).lower():
            hi = i
            break
    if hi is None:
        raise ValueError("Header row (Reach | Distance (km) | ...) not found: is this the 'WQ Output' sheet?")
    head = table[hi]
    ncol = max(head) + 1
    # stop at the first block break: columns after the constituent summary (rates, fluxes) start with '' header gaps
    names = [str(head.get(i, "")).strip() for i in range(ncol)]
    rows = []
    for t in table[hi + 1:]:
        km = _num(t.get(1))
        if km is None:
            if rows:
                break
            continue
        vals = {}
        for i in range(3, ncol):
            if names[i] and _num(t.get(i)) is not None:
                vals[names[i]] = float(t[i])
        rows.append({"label": str(t.get(0, "")).strip(), "km": km, "values": vals})
    if not rows:
        raise ValueError("No result rows below the header: run the model in the workbook first.")
    headers = [n for n in names[3:] if n and any(n in r["values"] for r in rows)]
    return headers, rows


def interpolate_km(rows, header, km):
    """Linear interpolation of a result column at a distance (km)."""
    pts = sorted((r["km"], r["values"][header]) for r in rows if header in r["values"])
    if not pts:
        return None
    if km <= pts[0][0]:
        return pts[0][1]
    for (k0, v0), (k1, v1) in zip(pts, pts[1:]):
        if k0 <= km <= k1:
            return v0 if k1 == k0 else v0 + (v1 - v0) * (km - k0) / (k1 - k0)
    return pts[-1][1]


def chainage_of(pts, x, y):
    """Chainage (m from pts[0]) of the point on the polyline closest to (x, y), and the distance to it."""
    best = (float("inf"), 0.0)
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / seg2))
        px, py = a[0] + dx * t, a[1] + dy * t
        d = math.hypot(x - px, y - py)
        seg = math.sqrt(seg2)
        if d < best[0]:
            best = (d, acc + seg * t)
        acc += seg
    return best[1], best[0]


def field_name(header):
    """'Dissolved oxygen (mgO2/L)' -> 'Dissolved_oxygen_mgO2_L' (safe GIS field name)."""
    s = re.sub(r"[^0-9A-Za-z]+", "_", header).strip("_")
    return s[:60] or "value"
