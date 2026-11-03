# -*- coding: utf-8 -*-
import os

from qgis.core import (Qgis, QgsFeature, QgsFields, QgsField, QgsGeometry, QgsPointXY, QgsProcessingException,
                       QgsProcessingParameterCrs, QgsProcessingParameterFeatureSink, QgsProcessingParameterFile)
from qgis.PyQt.QtCore import QMetaType

from ..core import aermod_io
from ..core.audit import AuditLog
from .base import EiaAlgorithm


class ImportAermodPlotfile(EiaAlgorithm):
    """Read an AERMOD PLOTFILE into a point layer of concentrations. Choose the CRS the model ran in (UTM)."""

    LEVEL = "A"

    def name(self):
        return "import_aermod_plotfile"

    def displayName(self):
        return "Import AERMOD plotfile as points"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("PLOTFILE", "AERMOD PLOTFILE", behavior=Qgis.ProcessingFileParameterBehavior.File))
        self.addParameter(QgsProcessingParameterCrs("CRS", "CRS of the model run (UTM)"))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Concentration points",
                                                            type=Qgis.ProcessingSourceType.VectorPoint))

    def prepareAlgorithm(self, parameters, context, feedback):
        self._path = self.parameterAsFile(parameters, "PLOTFILE", context)
        self._audit_dir = self.project_dir(os.path.dirname(os.path.abspath(self._path)))
        return True

    def processAlgorithm(self, parameters, context, feedback):
        rows = aermod_io.read_plotfile(self._path)
        if not rows:
            raise QgsProcessingException("No data rows found in %s" % self._path)
        crs = self.parameterAsCrs(parameters, "CRS", context)
        fields = QgsFields()
        fields.append(QgsField("conc", QMetaType.Type.Double))
        fields.append(QgsField("ave", QMetaType.Type.QString))
        fields.append(QgsField("grp", QMetaType.Type.QString))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, Qgis.WkbType.Point, crs)
        for r in rows:
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(r["x"], r["y"])))
            f.setAttributes([r["conc"], r["ave"], r["grp"]])
            sink.addFeature(f)
        feedback.pushInfo("%d receptors read" % len(rows))
        AuditLog(self._audit_dir).append(step="import_aermod_plotfile", level="A", model="aermod", card_version=None,
                                         parameters={"plotfile": self._path, "crs": crs.authid(), "n": len(rows)},
                                         files=[self._path])
        return {"OUTPUT": dest}
