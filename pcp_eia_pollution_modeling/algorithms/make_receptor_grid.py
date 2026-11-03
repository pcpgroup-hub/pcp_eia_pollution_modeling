# -*- coding: utf-8 -*-
from qgis.core import (Qgis, QgsCoordinateTransform, QgsFeature, QgsFields, QgsField, QgsGeometry, QgsPointXY,
                       QgsProcessingException, QgsProcessingParameterCrs, QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterNumber, QgsProject)
from qgis.PyQt.QtCore import QMetaType

from ..core import grid
from ..core.audit import AuditLog
from .base import EiaAlgorithm


class MakeReceptorGrid(EiaAlgorithm):
    """Regular grid of receptor points around the source layer, in a metric CRS (UTM). Source coordinates are
    transformed to that CRS first; the transformation is recorded in the audit log."""

    LEVEL = "A"

    def name(self):
        return "make_receptor_grid"

    def displayName(self):
        return "Make receptor grid around sources"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Source / discharge points",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterCrs("CRS", "Model CRS (UTM, metres), e.g. EPSG:32648 or 32649"))
        self.addParameter(QgsProcessingParameterNumber("RADIUS", "Distance around sources (m)",
                                                       QgsProcessingParameterNumber.Double, 5000, minValue=100))
        self.addParameter(QgsProcessingParameterNumber("SPACING", "Grid spacing (m)",
                                                       QgsProcessingParameterNumber.Double, 100, minValue=1))
        self.addParameter(QgsProcessingParameterNumber("INNER_RADIUS", "Fine inner grid: distance around sources (m, 0 = off)",
                                                       QgsProcessingParameterNumber.Double, 0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("INNER_SPACING", "Fine inner grid: spacing (m)",
                                                       QgsProcessingParameterNumber.Double, 100, minValue=1))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Receptor grid",
                                                            type=Qgis.ProcessingSourceType.VectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        src = self.parameterAsSource(parameters, "SOURCES", context)
        crs = self.parameterAsCrs(parameters, "CRS", context)
        if crs.isGeographic():
            raise QgsProcessingException("Model CRS must be projected (metres), not geographic.")
        tr = QgsCoordinateTransform(src.sourceCrs(), crs, QgsProject.instance().transformContext())
        pts = []
        for f in src.getFeatures():
            p = tr.transform(f.geometry().asPoint())
            pts.append((p.x(), p.y()))
        if not pts:
            raise QgsProcessingException("The source layer has no points.")
        try:
            box = grid.extent_around(pts, self.parameterAsDouble(parameters, "RADIUS", context))
            inner_r = self.parameterAsDouble(parameters, "INNER_RADIUS", context)
            if inner_r > 0:
                inner = grid.extent_around(pts, inner_r)
                nodes = grid.make_nested_grid(box, self.parameterAsDouble(parameters, "SPACING", context),
                                              inner, self.parameterAsDouble(parameters, "INNER_SPACING", context))
            else:
                nodes = grid.make_grid(*box, self.parameterAsDouble(parameters, "SPACING", context))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        fields = QgsFields()
        fields.append(QgsField("rid", QMetaType.Type.Int))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, Qgis.WkbType.Point, crs)
        for i, (x, y) in enumerate(nodes):
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([i + 1])
            sink.addFeature(f)
        feedback.pushInfo("%d receptors" % len(nodes))
        AuditLog(self.project_dir(".")).append(
            step="make_receptor_grid", level="A", model="aermod", card_version=None,
            parameters={"from_crs": src.sourceCrs().authid(), "to_crs": crs.authid(), "n": len(nodes),
                        "radius": self.parameterAsDouble(parameters, "RADIUS", context),
                        "spacing": self.parameterAsDouble(parameters, "SPACING", context)})
        return {"OUTPUT": dest}
