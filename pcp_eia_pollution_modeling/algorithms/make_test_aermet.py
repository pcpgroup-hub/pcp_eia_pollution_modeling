# -*- coding: utf-8 -*-
import os

from qgis.core import (QgsProcessingException, QgsProcessingOutputFile, QgsProcessingParameterFile,
                       QgsProcessingParameterNumber, QgsProcessingParameterString, QgsProcessingParameterFolderDestination)

from ..core import aermet_synth, met_hourly
from ..core.audit import AuditLog
from .base import EiaAlgorithm


class MakeTestAermet(EiaAlgorithm):
    """TEST ONLY. Writes AERMET-style .SFC and .PFL files from a simple hourly CSV (wind, temperature, stability class).
    The boundary-layer parameters are assumed from the stability class, not computed by AERMET from observations,
    so AERMOD results made with them are for trying the workflow and are not valid for a dossier."""

    LEVEL = "A"

    def name(self):
        return "make_test_aermet"

    def displayName(self):
        return "Make TEST AERMET files (.SFC/.PFL) from a simple hourly CSV"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("MET", "Hourly meteorology CSV (with Stability_Class column)", extension="csv"))
        self.addParameter(QgsProcessingParameterNumber("YEAR", "Year", QgsProcessingParameterNumber.Integer, 2024, minValue=1950, maxValue=2100))
        self.addParameter(QgsProcessingParameterNumber("LAT", "Latitude (deg)", QgsProcessingParameterNumber.Double, 11.3))
        self.addParameter(QgsProcessingParameterNumber("LON", "Longitude (deg)", QgsProcessingParameterNumber.Double, 108.8))
        self.addParameter(QgsProcessingParameterString("STATION", "Station id (digits)", "99999"))
        self.addParameter(QgsProcessingParameterNumber("Z0", "Surface roughness (m)", QgsProcessingParameterNumber.Double, 0.1, minValue=0.001))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Output folder"))
        self.addOutput(QgsProcessingOutputFile("SFC", "Surface file"))
        self.addOutput(QgsProcessingOutputFile("PFL", "Profile file"))

    def processAlgorithm(self, parameters, context, feedback):
        met = met_hourly.read_csv(self.parameterAsFile(parameters, "MET", context))
        if not met["hours"]:
            raise QgsProcessingException("No valid hours in the CSV.")
        st = self.parameterAsString(parameters, "STATION", context).strip() or "99999"
        sfc, pfl = aermet_synth.make_files(met["hours"], self.parameterAsInt(parameters, "YEAR", context),
                                           self.parameterAsDouble(parameters, "LAT", context), self.parameterAsDouble(parameters, "LON", context),
                                           st, z0=self.parameterAsDouble(parameters, "Z0", context))
        out = self.parameterAsString(parameters, "OUTDIR", context)
        os.makedirs(out, exist_ok=True)
        a, b = os.path.join(out, "test_met.sfc"), os.path.join(out, "test_met.pfl")
        for p, t in ((a, sfc), (b, pfl)):
            with open(p, "w", newline="\n") as fh:
                fh.write(t)
        feedback.pushWarning("TEST ONLY: boundary-layer parameters are assumed from the stability class. Not valid for a dossier.")
        AuditLog(self.project_dir(out)).append(step="make_test_aermet", level="A", model="synthetic_met", card_version=None,
                                               parameters={"hours": len(met["hours"]), "station": st, "note": "assumed parameters, test only"}, files=[a, b])
        return {"SFC": a, "PFL": b}
