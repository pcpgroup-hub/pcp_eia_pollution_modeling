# -*- coding: utf-8 -*-
import os

from qgis.core import (Qgis, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterCrs, QgsProcessingParameterEnum, QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterNumber,
                       QgsProcessingParameterString, QgsProject)
from qgis.PyQt.QtCore import QMetaType

from ..core import gauss, gauss_np
from ..core.audit import AuditLog
from .base import EiaAlgorithm

_FIELDS = [("EMIS", "Emission rate field (g/s)"), ("HEIGHT", "Stack height field (m)"),
           ("TEMP", "Exit temperature field (deg C)"), ("VEL", "Exit velocity field (m/s)"),
           ("DIAM", "Stack diameter field (m)")]
_CLASSES = ["A", "B", "C", "D", "E", "F"]


class GaussScreening(EiaAlgorithm):
    """Quick screening with a simple Gaussian plume: ONE wind speed, ONE wind direction, ONE stability class,
    flat terrain. It is NOT AERMOD and not a regulatory result; use it to preview a map or compare scenarios.
    Works on any receptor points (grid or sensitive points). If a limit is given, ratio and exceedance are added."""

    LEVEL = "A"

    def name(self):
        return "gauss_screening"

    def displayName(self):
        return "Screening plume (simple Gauss, not AERMOD)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Source / stack points",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        for key, label in _FIELDS:
            self.addParameter(QgsProcessingParameterField(key, label, parentLayerParameterName="SOURCES",
                                                          type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterFeatureSource("RECEPTORS", "Receptor points",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterCrs("CRS", "Model CRS (UTM, metres)"))
        self.addParameter(QgsProcessingParameterNumber("WIND", "Wind speed (m/s)", QgsProcessingParameterNumber.Double, 3.0, minValue=0.5))
        self.addParameter(QgsProcessingParameterNumber("FROM", "Wind blows FROM (degrees, 0 = north)",
                                                       QgsProcessingParameterNumber.Double, 225, minValue=0, maxValue=360))
        self.addParameter(QgsProcessingParameterString("ROSE", "Wind rose (optional): 16 frequencies, wind FROM N, NNE, ... NNW, in % - if given, the direction above is ignored and the long-term sector average is computed", "", optional=True))
        self.addParameter(QgsProcessingParameterBoolean("ENV", "Highest-value envelope ('1st high'): maximum over many wind directions, speeds and stability classes (overrides direction and rose)", False))
        self.addParameter(QgsProcessingParameterString("DIRS", "Envelope: wind-from directions in degrees (empty = every 2 degrees; with a wind rose, directions whose frequency is below 1% are left out)", "", optional=True))
        self.addParameter(QgsProcessingParameterString("SPEEDS", "Envelope: wind speeds m/s", "1.5 3 5", optional=True))
        self.addParameter(QgsProcessingParameterString("STABS", "Envelope: stability classes (F is left out by default: with a steady plume it overstates values far from the source)", "B D", optional=True))
        self.addParameter(QgsProcessingParameterNumber("AVGF", "Envelope: averaging-time factor (1 = 1 h; expert may set e.g. 0.4 for 24 h)", QgsProcessingParameterNumber.Double, 1.0, minValue=0.01, maxValue=1.0))
        self.addParameter(QgsProcessingParameterEnum("STAB", "Pasquill stability class", _CLASSES, defaultValue=3))
        self.addParameter(QgsProcessingParameterNumber("AMB", "Ambient temperature (K)", QgsProcessingParameterNumber.Double, 298.0))
        self.addParameter(QgsProcessingParameterString("LIMIT", "Limit to compare with (ug/m3, optional)", "", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Concentration (ug/m3)", type=Qgis.ProcessingSourceType.VectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        crs = self.parameterAsCrs(parameters, "CRS", context)
        if crs.isGeographic():
            raise QgsProcessingException("Model CRS must be projected (metres).")
        ctx = QgsProject.instance().transformContext()
        src = self.parameterAsSource(parameters, "SOURCES", context)
        rec = self.parameterAsSource(parameters, "RECEPTORS", context)
        fld = {k: self.parameterAsString(parameters, k, context) for k, _ in _FIELDS}
        tr = QgsCoordinateTransform(src.sourceCrs(), crs, ctx)
        sources = []
        for feat in src.getFeatures():
            p = tr.transform(feat.geometry().asPoint())
            try:
                sources.append(dict(x=p.x(), y=p.y(), emis=float(feat[fld["EMIS"]]), height=float(feat[fld["HEIGHT"]]),
                                    temp=float(feat[fld["TEMP"]]) + 273.15, vel=float(feat[fld["VEL"]]),
                                    diam=float(feat[fld["DIAM"]])))
            except (TypeError, ValueError):
                raise QgsProcessingException("A source has an empty or non-numeric value in the chosen fields.")
        if not sources:
            raise QgsProcessingException("No sources.")
        u = self.parameterAsDouble(parameters, "WIND", context)
        wd = self.parameterAsDouble(parameters, "FROM", context)
        st = _CLASSES[self.parameterAsEnum(parameters, "STAB", context)]
        amb = self.parameterAsDouble(parameters, "AMB", context)
        rose_txt = self.parameterAsString(parameters, "ROSE", context).strip()
        try:
            rose = gauss.parse_rose(rose_txt) if rose_txt else None
        except ValueError as e:
            raise QgsProcessingException(str(e))
        lim_txt = self.parameterAsString(parameters, "LIMIT", context).strip().replace(",", ".")
        try:
            limit = float(lim_txt) if lim_txt else None
        except ValueError:
            raise QgsProcessingException("Limit must be a number.")
        env = self.parameterAsBool(parameters, "ENV", context)
        env_vals = None
        if env:
            import re
            try:
                dtxt = self.parameterAsString(parameters, "DIRS", context).strip()
                dirs = [float(t) for t in re.split(r"[\s;,]+", dtxt) if t] or [float(d) for d in range(0, 360, 2)]
                speeds = [float(t) for t in re.split(r"[\s;,]+", self.parameterAsString(parameters, "SPEEDS", context).strip()) if t] or [3.0]
                stabs = [t.upper() for t in re.split(r"[\s;,]+", self.parameterAsString(parameters, "STABS", context).strip()) if t] or ["D"]
            except ValueError:
                raise QgsProcessingException("Directions and speeds must be numbers.")
            if any(t not in _CLASSES for t in stabs):
                raise QgsProcessingException("Stability classes must be letters A-F.")
            if rose and not dtxt:
                dirs = [d for d in dirs if gauss._rose_freq(rose, d) >= 0.01] or dirs
            avgf = self.parameterAsDouble(parameters, "AVGF", context)
            import numpy as np
            trr0 = QgsCoordinateTransform(rec.sourceCrs(), crs, ctx)
            pts = [trr0.transform(f.geometry().asPoint()) for f in rec.getFeatures()]
            X = np.array([p.x() for p in pts])
            Y = np.array([p.y() for p in pts])
            try:
                env_vals = gauss_np.first_high(sources, X, Y, dirs, speeds, stabs, amb, avgf)
            except ValueError as e:
                raise QgsProcessingException(str(e))
        fields = QgsFields()
        fields.append(QgsField("conc", QMetaType.Type.Double))
        if limit:
            fields.append(QgsField("limit", QMetaType.Type.Double))
            fields.append(QgsField("ratio", QMetaType.Type.Double))
            fields.append(QgsField("exceed", QMetaType.Type.Int))
        for fdef in rec.fields():
            fields.append(QgsField(fdef.name() if fields.indexFromName(fdef.name()) < 0 else "r_" + fdef.name(), fdef.type()))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, Qgis.WkbType.Point, crs)
        trr = QgsCoordinateTransform(rec.sourceCrs(), crs, ctx)
        n, mx = 0, 0.0
        total = rec.featureCount() or 1
        for i, feat in enumerate(rec.getFeatures()):
            if feedback.isCanceled():
                break
            p = trr.transform(feat.geometry().asPoint())
            try:
                c = float(env_vals[i]) if env_vals is not None else (sum(gauss.sector_conc(s, p.x(), p.y(), u, rose, st, amb) for s in sources) if rose
                     else sum(gauss.ground_conc(s, p.x(), p.y(), u, wd, st, amb) for s in sources))
            except ValueError as e:
                raise QgsProcessingException(str(e))
            mx = max(mx, c)
            out = QgsFeature(fields)
            out.setGeometry(QgsGeometry.fromPointXY(p))
            attrs = [c]
            if limit:
                attrs += [limit, c / limit, 1 if c > limit else 0]
            out.setAttributes(attrs + list(feat.attributes()))
            sink.addFeature(out)
            n += 1
            if i % 500 == 0:
                feedback.setProgress(100.0 * i / total)
        ext = rec.sourceExtent()
        too, sp, half = gauss.grid_too_coarse(n, ext.width() * ext.height(), st)
        if too and n > 50 and not rose and not env:
            feedback.pushWarning("Receptor spacing (about %.0f m) is wider than half the plume width at 500 m (%.0f m): "
                                 "contours will look like separate beads. Use a finer grid (e.g. 25-50 m) for a single-wind map." % (sp, half))
        feedback.pushInfo("Simple Gauss, NOT AERMOD. %d points, max %.2f ug/m3 (u=%.1f m/s from %.0f deg, class %s)" % (n, mx, u, wd, st))
        AuditLog(self.project_dir(".")).append(
            step="gauss_screening", level="A", model="gauss_simple", card_version=None,
            parameters={"model_crs": crs.authid(), "n_sources": len(sources), "n_receptors": n, "wind_ms": u,
                        "wind_from_deg": None if (rose or env) else wd, "envelope": ({"dirs": dirs, "speeds": speeds, "stabs": stabs, "factor": avgf} if env else None), "wind_rose_16": rose, "stability": st, "ambient_K": amb, "limit": limit, "max_ugm3": mx,
                        "note": "screening only, not AERMOD"})
        return {"OUTPUT": dest}
