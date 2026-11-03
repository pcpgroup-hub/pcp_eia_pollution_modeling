# -*- coding: utf-8 -*-
import os

from qgis.core import (Qgis, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterCrs, QgsProcessingParameterEnum, QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFile, QgsProcessingParameterNumber,
                       QgsProcessingParameterString, QgsProject, QgsProcessingOutputString)
from qgis.PyQt.QtCore import QMetaType

from ..core import hourly, met_hourly
from ..core.audit import AuditLog
from .base import EiaAlgorithm

_FIELDS = [("EMIS", "Emission rate field (g/s)"), ("HEIGHT", "Stack height field (m)"),
           ("TEMP", "Exit temperature field (deg C)"), ("VEL", "Exit velocity field (m/s)"),
           ("DIAM", "Stack diameter field (m)")]
_STATS = ["Highest 1-hour value (1st high)", "Highest 24-hour mean (calendar day)", "Mean of the selected period (annual if the record is a full year)"]


class HourlyScreening(EiaAlgorithm):
    """Hour-by-hour simple Gaussian plume over an hourly meteorological record (CSV made from an AERMET .SFC file):
    gives the highest 1-h value, the highest 24-h mean or the period mean at every receptor. Optional month filter for
    seasons. NOT AERMOD: flat terrain, no building downwash, stability classes taken from the Monin-Obukhov length."""

    LEVEL = "A"

    def name(self):
        return "hourly_screening"

    def displayName(self):
        return "Hourly screening plume (met record, simple Gauss, not AERMOD)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Source / stack points", [Qgis.ProcessingSourceType.VectorPoint]))
        for key, label in _FIELDS:
            self.addParameter(QgsProcessingParameterField(key, label, parentLayerParameterName="SOURCES", type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterFeatureSource("RECEPTORS", "Receptor points", [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterCrs("CRS", "Model CRS (UTM, metres)"))
        self.addParameter(QgsProcessingParameterFile("MET", "Hourly meteorology CSV (AERMET surface file as CSV)", extension="csv"))
        self.addParameter(QgsProcessingParameterEnum("STAT", "Result", _STATS, defaultValue=0))
        self.addParameter(QgsProcessingParameterString("MONTHS", "Months to use (e.g. '12 1 2' for a season; empty = all)", "", optional=True))
        self.addParameter(QgsProcessingParameterNumber("MINWS", "Minimum wind speed (m/s); slower hours are raised to it", QgsProcessingParameterNumber.Type.Double, 1.0, minValue=0.1))
        self.addParameter(QgsProcessingParameterNumber("MEANDER", "Wind-direction meander (0 = off, 1 = standard sigma-theta by stability class, 2 = double): widens each hour's plume sideways so that few hours do not give separate thin rays", QgsProcessingParameterNumber.Type.Double, 1.0, minValue=0.0, maxValue=4.0))
        self.addParameter(QgsProcessingParameterString("LIMIT", "Limit to compare with (ug/m3, optional)", "", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Concentration (ug/m3)", type=Qgis.ProcessingSourceType.VectorPoint))
        self.addOutput(QgsProcessingOutputString("MET_SUMMARY", "Meteorology summary"))
        self.addOutput(QgsProcessingOutputString("WHEN_MAX", "Time of the highest value"))

    def processAlgorithm(self, parameters, context, feedback):
        import re
        import numpy as np
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
                                    temp=float(feat[fld["TEMP"]]) + 273.15, vel=float(feat[fld["VEL"]]), diam=float(feat[fld["DIAM"]])))
            except (TypeError, ValueError, KeyError):
                raise QgsProcessingException("A source has an empty or non-numeric value in the chosen fields.")
        if not sources:
            raise QgsProcessingException("No sources.")
        try:
            met = met_hourly.read_csv(self.parameterAsFile(parameters, "MET", context))
        except (OSError, UnicodeDecodeError) as e:
            raise QgsProcessingException("Cannot read the meteorology file: %s" % e)
        if not met["hours"]:
            raise QgsProcessingException("No valid hours found in the meteorology file (needs the AERMET surface columns).")
        mtxt = self.parameterAsString(parameters, "MONTHS", context)
        try:
            months = set(int(t) for t in re.split(r"[\s;,]+", mtxt.strip()) if t) or None
        except ValueError:
            raise QgsProcessingException("Months must be numbers 1-12.")
        if months and any(m < 1 or m > 12 for m in months):
            raise QgsProcessingException("Months must be numbers 1-12.")
        lim_txt = self.parameterAsString(parameters, "LIMIT", context).strip().replace(",", ".")
        try:
            limit = float(lim_txt) if lim_txt else None
        except ValueError:
            raise QgsProcessingException("Limit must be a number.")
        statkey = hourly.STATS[self.parameterAsEnum(parameters, "STAT", context)]
        trr = QgsCoordinateTransform(rec.sourceCrs(), crs, ctx)
        feats = list(rec.getFeatures())
        pts = [trr.transform(f.geometry().asPoint()) for f in feats]
        X = np.array([p.x() for p in pts])
        Y = np.array([p.y() for p in pts])
        res = hourly.run(sources, X, Y, met["hours"], statkey, months, self.parameterAsDouble(parameters, "MINWS", context),
                         progress=feedback.setProgress, meander=self.parameterAsDouble(parameters, "MEANDER", context) > 0,
                         theta_scale=self.parameterAsDouble(parameters, "MEANDER", context))
        vals = res["field"]
        fields = QgsFields()
        fields.append(QgsField("conc", QMetaType.Type.Double))
        if limit:
            fields.append(QgsField("limit", QMetaType.Type.Double))
            fields.append(QgsField("ratio", QMetaType.Type.Double))
            fields.append(QgsField("exceed", QMetaType.Type.Int))
        for fdef in rec.fields():
            fields.append(QgsField(fdef.name() if fields.indexFromName(fdef.name()) < 0 else "r_" + fdef.name(), fdef.type()))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, Qgis.WkbType.Point, crs)
        for i, feat in enumerate(feats):
            c = float(vals[i])
            out = QgsFeature(fields)
            out.setGeometry(QgsGeometry.fromPointXY(pts[i]))
            attrs = [c]
            if limit:
                attrs += [limit, c / limit, 1 if c > limit else 0]
            out.setAttributes(attrs + list(feat.attributes()))
            sink.addFeature(out)
        summary = "%d h used of %d read (%d unreadable, %d calm raised to %.1f m/s); classes %s%s" % (
            res["n_used"], len(met["hours"]), met["bad_rows"] + met["missing"], res["n_calm"],
            self.parameterAsDouble(parameters, "MINWS", context), res["classes"],
            ("; max at %s" % res["when_max"]) if res["when_max"] else "")
        if res["n_used"] < 8000 and not months:
            feedback.pushWarning("The record has only %d h: the 'annual' and 'highest' values are for this record, not for a full year." % res["n_used"])
        feedback.pushInfo("Hourly simple Gauss, NOT AERMOD. %s. Max %.2f ug/m3" % (summary, float(vals.max())))
        AuditLog(self.project_dir(".")).append(
            step="hourly_screening", level="A", model="gauss_simple_hourly", card_version=None,
            parameters={"model_crs": crs.authid(), "n_sources": len(sources), "n_receptors": len(feats), "stat": statkey,
                        "months": sorted(months) if months else None, "hours_used": res["n_used"], "max_ugm3": float(vals.max()),
                        "met_file": self.parameterAsFile(parameters, "MET", context), "note": "screening only, not AERMOD"})
        return {"OUTPUT": dest, "MET_SUMMARY": summary, "WHEN_MAX": res["when_max"]}
