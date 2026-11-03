# -*- coding: utf-8 -*-
import os

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields,
                       QgsGeometry, QgsPointXY, QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterFeatureSink, QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber,
                       QgsProcessingParameterVectorLayer, QgsProject)
from qgis.PyQt.QtCore import QMetaType

from ..core import qual2kw_io as q
from ..core.audit import AuditLog
from .base import EiaAlgorithm


def _river_points(layer, reverse):
    """Merge the river features into one polyline (list of (x, y)), headwater first."""
    geoms = [f.geometry() for f in layer.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
    if not geoms:
        raise QgsProcessingException("River layer has no line geometry")
    g = QgsGeometry.unaryUnion(geoms) if len(geoms) > 1 else geoms[0]
    g = g.mergeLines() if len(geoms) > 1 else g
    parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
    parts = [p for p in parts if len(p) > 1]
    if len(parts) != 1:
        raise QgsProcessingException("River must be ONE connected line (found %d parts). Merge or dissolve it first." % len(parts))
    pts = [(p.x(), p.y()) for p in parts[0]]
    return pts[::-1] if reverse else pts


class Qual2kwBuildInput(EiaAlgorithm):
    """Prepare tables for the official QUAL2Kw workbook from QGIS layers: Reach table and Point Sources table
    (CSV, same order as the workbook sheets, ready to paste). The plugin does not run or contain QUAL2Kw;
    the expert runs the official workbook on Windows. Distances: km upstream from the downstream end (QUAL2Kw convention).
    Point layer fields (all optional): name, q_in, q_out, temp, cond, iss, do, cbods, cbodf, orgn, nh4, no3, orgp, srp."""

    LEVEL = "A"

    def name(self):
        return "qual2kw_build_input"

    def displayName(self):
        return "QUAL2Kw: build Reach and Point Sources tables"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer("RIVER", "River centre line (projected CRS)",
                                                            [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer("POINTS", "Discharge / abstraction points (optional)",
                                                            [Qgis.ProcessingSourceType.VectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterNumber("REACH_KM", "Reach length (km)", Qgis.ProcessingNumberParameterType.Double, 1.0, minValue=0.01))
        self.addParameter(QgsProcessingParameterBoolean("REVERSE", "River line is digitised from mouth to headwater (reverse it)", False))
        self.addParameter(QgsProcessingParameterNumber("ELEV_UP", "Headwater elevation (m, optional)", Qgis.ProcessingNumberParameterType.Double, optional=True))
        self.addParameter(QgsProcessingParameterNumber("ELEV_DOWN", "Mouth elevation (m, optional)", Qgis.ProcessingNumberParameterType.Double, optional=True))
        self.addParameter(QgsProcessingParameterNumber("MAX_OFFSET", "Warn if a point is farther than this from the river (m)", Qgis.ProcessingNumberParameterType.Double, 500.0, minValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Output folder"))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, "RIVER", context)
        if layer.crs().isGeographic():
            raise QgsProcessingException("Reproject the river to a metric CRS (e.g. UTM) first.")
        pts = _river_points(layer, self.parameterAsBool(parameters, "REVERSE", context))
        tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())

        def to_lonlat(x, y):
            p = tr.transform(QgsPointXY(x, y))
            return p.x(), p.y()

        eu = parameters.get("ELEV_UP")
        ed = parameters.get("ELEV_DOWN")
        eu = float(eu) if eu not in (None, "") else None
        ed = float(ed) if ed not in (None, "") else None
        rows = q.build_reach_rows(pts, to_lonlat, self.parameterAsDouble(parameters, "REACH_KM", context), eu, ed)
        out = self.parameterAsString(parameters, "OUTDIR", context)
        os.makedirs(out, exist_ok=True)
        total = q.polyline_length(pts)
        q.write_reach_csv(os.path.join(out, "reach.csv"), rows)
        feedback.pushInfo("River length %.3f km, %d reaches -> reach.csv" % (total / 1000.0, len(rows) - 1))

        src_rows = []
        pl = self.parameterAsVectorLayer(parameters, "POINTS", context)
        maxoff = self.parameterAsDouble(parameters, "MAX_OFFSET", context)
        if pl is not None:
            ptr = QgsCoordinateTransform(pl.crs(), layer.crs(), QgsProject.instance())
            names = [f.name().lower() for f in pl.fields()]
            real = {f.name().lower(): f.name() for f in pl.fields()}
            for f in pl.getFeatures():
                if not f.hasGeometry():
                    continue
                p = ptr.transform(f.geometry().asPoint())
                s, off = q.chainage_of(pts, p.x(), p.y())
                if off > maxoff:
                    feedback.reportError("Point '%s' is %.0f m from the river: check its position" % (f[real["name"]] if "name" in names else f.id(), off))
                r = {"name": f[real["name"]] if "name" in names else "P%d" % f.id(), "km": (total - s) / 1000.0}
                for key, _, _ in q.SOURCE_FIELDS:
                    if key in names and f[real[key]] not in (None, ""):
                        r[key] = f[real[key]]
                src_rows.append(r)
            src_rows.sort(key=lambda r: -r["km"])
            q.write_sources_csv(os.path.join(out, "point_sources.csv"), src_rows)
            feedback.pushInfo("%d points -> point_sources.csv" % len(src_rows))
        AuditLog(self.project_dir(out)).append(step="qual2kw_build_input", level="B", model="qual2kw", card_version=None,
                                               parameters={"river": layer.name(), "reaches": len(rows) - 1, "points": len(src_rows)},
                                               files=[os.path.join(out, "reach.csv")])
        return {"OUTDIR": out}


class Qual2kwImportResults(EiaAlgorithm):
    """Read the 'WQ Output' sheet of a QUAL2Kw workbook the expert has run (xlsm/xlsx, or that sheet saved as CSV)
    and attach the results to the river line, one segment per result interval, one field per constituent.
    The river line is scaled to the model's km so small length differences do not matter."""

    LEVEL = "A"

    def name(self):
        return "qual2kw_import_results"

    def displayName(self):
        return "QUAL2Kw: import results onto the river"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer("RIVER", "River centre line (projected CRS)",
                                                            [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterFile("RESULTS", "Run workbook (.xlsm/.xlsx) or WQ Output saved as .csv"))
        self.addParameter(QgsProcessingParameterBoolean("REVERSE", "River line is digitised from mouth to headwater (reverse it)", False))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "River with results", type=Qgis.ProcessingSourceType.VectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, "RIVER", context)
        path = self.parameterAsFile(parameters, "RESULTS", context)
        pts = _river_points(layer, self.parameterAsBool(parameters, "REVERSE", context))
        if path.lower().endswith(".csv"):
            headers, rows = q.read_wq_output_csv(path)
        else:
            headers, rows = q.read_wq_output_xlsx(path)
        feedback.pushInfo("%d result rows, %d constituents" % (len(rows), len(headers)))
        kms = sorted({r["km"] for r in rows}, reverse=True)
        if len(kms) < 2:
            raise QgsProcessingException("Need at least two distances in the results")
        kmax, total = kms[0], q.polyline_length(pts)
        fields = QgsFields()
        fields.append(QgsField("km_from", QMetaType.Type.Double))
        fields.append(QgsField("km_to", QMetaType.Type.Double))
        used = {}
        for h in headers:
            fn = q.field_name(h)
            used[h] = fn
            fields.append(QgsField(fn, QMetaType.Type.Double))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, Qgis.WkbType.LineString, layer.crs())
        for k0, k1 in zip(kms, kms[1:]):
            s0, s1 = (kmax - k0) / kmax * total, (kmax - k1) / kmax * total
            line = q.sub_line(pts, s0, s1)
            if len(line) < 2:
                continue
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in line]))
            mid = (k0 + k1) / 2.0
            f.setAttributes([k0, k1] + [q.interpolate_km(rows, h, mid) for h in headers])
            sink.addFeature(f)
        if abs(kmax * 1000 - total) > 0.05 * total:
            feedback.reportError("River line is %.2f km but the model's headwater is at km %.2f: results were stretched to fit. Check the river layer." % (total / 1000.0, kmax))
        AuditLog(self.project_dir(os.path.dirname(os.path.abspath(path)))).append(
            step="qual2kw_import_results", level="A", model="qual2kw", card_version=None,
            parameters={"results": path, "segments": len(kms) - 1}, files=[path])
        return {"OUTPUT": dest}
