# -*- coding: utf-8 -*-
"""Receptor grid and UTM helpers. No QGIS imports."""
import math


def utm_epsg_for_lonlat(lon, lat):
    """EPSG code of the WGS84 UTM zone containing the point (north or south)."""
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def make_grid(xmin, ymin, xmax, ymax, spacing, max_points=250000):
    """Regular grid of (x, y) nodes covering the extent, row by row from the south-west.

    Raises ValueError for a bad spacing or a grid larger than `max_points`
    (AERMOD gets slow and the plot unreadable long before that).
    """
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("extent is empty")
    nx = int(math.floor((xmax - xmin) / spacing)) + 1
    ny = int(math.floor((ymax - ymin) / spacing)) + 1
    if nx * ny > max_points:
        raise ValueError("grid would have %d points (limit %d); increase spacing" % (nx * ny, max_points))
    return [(xmin + i * spacing, ymin + j * spacing) for j in range(ny) for i in range(nx)]


def extent_around(points, radius):
    """Bounding box of `points` grown by `radius` on every side."""
    if not points:
        raise ValueError("no points")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius


def make_nested_grid(outer_box, outer_step, inner_box, inner_step, max_points=250000):
    """Fine grid inside `inner_box`, coarse grid over `outer_box` outside it (no duplicates).

    Boxes are (xmin, ymin, xmax, ymax). Mirrors the usual EIA set-up (e.g. 200 m up to
    2 km, 500 m beyond). The inner box must lie inside the outer one.
    """
    ox0, oy0, ox1, oy1 = outer_box
    ix0, iy0, ix1, iy1 = inner_box
    if not (ox0 <= ix0 and oy0 <= iy0 and ix1 <= ox1 and iy1 <= oy1):
        raise ValueError("inner box must lie inside the outer box")
    inner = make_grid(ix0, iy0, ix1, iy1, inner_step, max_points)
    outer = [p for p in make_grid(ox0, oy0, ox1, oy1, outer_step, max_points)
             if not (ix0 - 1e-6 <= p[0] <= ix1 + 1e-6 and iy0 - 1e-6 <= p[1] <= iy1 + 1e-6)]
    if len(inner) + len(outer) > max_points:
        raise ValueError("grid would exceed %d points" % max_points)
    return inner + outer
