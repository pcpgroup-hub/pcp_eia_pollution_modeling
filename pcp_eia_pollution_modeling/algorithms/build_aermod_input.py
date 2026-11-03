# -*- coding: utf-8 -*-
import os

from qgis.core import (Qgis, QgsCoordinateTransform, QgsProcessingException, QgsProcessingParameterCrs,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber,
                       QgsProcessingParameterString, QgsProcessingParameterBoolean, QgsProject)

from ..core import aermod_input
from ..core.audit import AuditLog
from .base import EiaAlgorithm

_NUM = [("EMIS", "Emission rate field (g/s)"), ("HEIGHT", "Stack height field (m)"),
        ("TEMP", "Exit temperature field (K)"), ("VEL", "Exit velocity field (m/s)"),
        ("DIAM", "Stack diameter field (m)")]


class BuildAermodInput(EiaAlgorithm):
    """Write an AERMOD control file from a source point layer and a receptor point layer. Coordinates are
    transformed to the model CRS. Meteorology files, station ids and year are chosen by the expert; the plugin
    only checks that the files exist. Does not run the model."""

    LEVEL = "A"

    def name(self):
        return "build_aermod_input"

    def displayName(self):
        return "Build AERMOD input from layers"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Source points",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterField("ID", "Source id field (1-8 letters/digits)", parentLayerParameterName="SOURCES"))
        for key, label in _NUM:
            self.addParameter(QgsProcessingParameterField(key, label, parentLayerParameterName="SOURCES",
                                                          type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterFeatureSource("RECEPTORS", "Receptor points (model CRS)",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterCrs("CRS", "Model CRS (UTM, metres)"))
        self.addParameter(QgsProcessingParameterString("POLLUTANT", "Pollutant id (e.g. SO2, NO2, PM10)", "SO2"))
        self.addParameter(QgsProcessingParameterString("AVG", "Averaging times, space separated (hours or PERIOD)", "1 24 PERIOD"))
        self.addParameter(QgsProcessingParameterFile("SURF", "Surface meteorology file (.SFC)"))
        self.addParameter(QgsProcessingParameterFile("PROF", "Profile meteorology file (.PFL)"))
        self.addParameter(QgsProcessingParameterString("SURF_ST", "Surface station id", ""))
        self.addParameter(QgsProcessingParameterNumber("SURF_YR", "Surface data year", QgsProcessingParameterNumber.Integer, 2020))
        self.addParameter(QgsProcessingParameterString("UA_ST", "Upper-air station id", ""))
        self.addParameter(QgsProcessingParameterNumber("UA_YR", "Upper-air data year", QgsProcessingParameterNumber.Integer, 2020))
        self.addParameter(QgsProcessingParameterNumber("BASE", "Profile base elevation (m)", QgsProcessingParameterNumber.Double, 0))
        self.addParameter(QgsProcessingParameterBoolean("DFAULT", "Use regulatory defaults (DFAULT)", True))
        self.addParameter(QgsProcessingParameterString("TITLE", "Scenario title", "Scenario 1"))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Scenario folder"))

    def processAlgorithm(self, parameters, context, feedback):
        crs = self.parameterAsCrs(parameters, "CRS", context)
        if crs.isGeographic():
            raise QgsProcessingException("Model CRS must be projected (metres).")
        ctx = QgsProject.instance().transformContext()
        src = self.parameterAsSource(parameters, "SOURCES", context)
        rec = self.parameterAsSource(parameters, "RECEPTORS", context)
        f = {k: self.parameterAsString(parameters, k, context) for k, _ in _NUM}
        idf = self.parameterAsString(parameters, "ID", context)
        tr = QgsCoordinateTransform(src.sourceCrs(), crs, ctx)
        sources = []
        for feat in src.getFeatures():
            p = tr.transform(feat.geometry().asPoint())
            d = dict(id=str(feat[idf]), x=p.x(), y=p.y(), z=0)
            for k, _ in _NUM:
                try:
                    d[k.lower()] = float(feat[f[k]])
                except (TypeError, ValueError):
                    raise QgsProcessingException("Source %s: field %s is empty or not a number" % (d["id"], f[k]))
            sources.append(d)
        trr = QgsCoordinateTransform(rec.sourceCrs(), crs, ctx)
        receptors = []
        for feat in rec.getFeatures():
            p = trr.transform(feat.geometry().asPoint())
            receptors.append((p.x(), p.y()))
        surf = self.parameterAsFile(parameters, "SURF", context)
        prof = self.parameterAsFile(parameters, "PROF", context)
        for pth in (surf, prof):
            if not os.path.isfile(pth):
                raise QgsProcessingException("Meteorology file not found: %s" % pth)
        outdir = self.parameterAsString(parameters, "OUTDIR", context)
        os.makedirs(outdir, exist_ok=True)
        # AERMOD reads the files from its working folder: copy names only, expert keeps the originals
        surf_name, prof_name = os.path.basename(surf), os.path.basename(prof)
        try:
            text = aermod_input.build_inp(
                self.parameterAsString(parameters, "TITLE", context),
                self.parameterAsString(parameters, "POLLUTANT", context), sources, receptors,
                surf_name, prof_name,
                self.parameterAsString(parameters, "SURF_ST", context), self.parameterAsInt(parameters, "SURF_YR", context),
                self.parameterAsString(parameters, "UA_ST", context), self.parameterAsInt(parameters, "UA_YR", context),
                self.parameterAsDouble(parameters, "BASE", context),
                avg_times=tuple(self.parameterAsString(parameters, "AVG", context).split()),
                dfault=self.parameterAsBoolean(parameters, "DFAULT", context))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        import shutil
        for pth in (surf, prof):
            dst = os.path.join(outdir, os.path.basename(pth))
            if os.path.abspath(pth) != os.path.abspath(dst):
                shutil.copy2(pth, dst)
        inp = os.path.join(outdir, "aermod.inp")
        with open(inp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        feedback.pushInfo("%d sources, %d receptors -> %s" % (len(sources), len(receptors), inp))
        AuditLog(self.project_dir(outdir)).append(
            step="build_aermod_input", level="A", model="aermod", card_version=None,
            parameters={"model_crs": crs.authid(), "sources_crs": src.sourceCrs().authid(),
                        "receptors_crs": rec.sourceCrs().authid(), "n_sources": len(sources),
                        "n_receptors": len(receptors), "dfault": self.parameterAsBoolean(parameters, "DFAULT", context),
                        "surf_station": self.parameterAsString(parameters, "SURF_ST", context),
                        "ua_station": self.parameterAsString(parameters, "UA_ST", context)},
            files=[inp, surf, prof])
        return {"OUTDIR": outdir, "INP": inp}
