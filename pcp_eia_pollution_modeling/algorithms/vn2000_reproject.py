# -*- coding: utf-8 -*-
import processing
from qgis.core import (QgsCoordinateReferenceSystem, QgsProcessingException, QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource)

from ..core import vn2000
from .base import EiaAlgorithm


class Vn2000Reproject(EiaAlgorithm):
    """Reproject a layer to VN-2000 TM-3 (3-degree zone) of the chosen province (central meridian from
    Thong tu 973/2001/TT-TCDC). Province names follow 2001; for merged provinces choose the one that contains the project
    and check the zone against the current regulation. AERMOD still needs metric coordinates: use the same CRS for the whole run."""

    LEVEL = "A"

    def name(self):
        return "vn2000_reproject"

    def displayName(self):
        return "VN-2000: reproject to the TM-3 zone of a province"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("INPUT", "Input layer"))
        self.addParameter(QgsProcessingParameterEnum("PROVINCE", "Province / city (central meridian by Thong tu 973/2001/TT-TCDC)",
                                                     options=["%s (%s)" % (n, vn2000.dms_label(m)) for n, m in vn2000.PROVINCES], defaultValue=0))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Reprojected layer"))

    def processAlgorithm(self, parameters, context, feedback):
        idx = self.parameterAsEnum(parameters, "PROVINCE", context)
        name, mer = vn2000.PROVINCES[idx]
        crs = QgsCoordinateReferenceSystem("EPSG:%d" % vn2000.EPSG_BY_MERIDIAN[mer])
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem.fromProj(vn2000.proj_string(mer))
        if not crs.isValid():
            raise QgsProcessingException("Cannot build the VN-2000 TM-3 CRS for %s" % name)
        feedback.pushInfo("%s: kinh tuyến trục %s -> %s" % (name, vn2000.dms_label(mer), crs.description()))
        res = processing.run("native:reprojectlayer", {"INPUT": parameters["INPUT"], "TARGET_CRS": crs, "OUTPUT": parameters["OUTPUT"]},
                             context=context, feedback=feedback, is_child_algorithm=True)
        return {"OUTPUT": res["OUTPUT"]}
