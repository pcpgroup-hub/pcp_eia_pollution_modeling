# -*- coding: utf-8 -*-
import os

from qgis.core import QgsProcessingAlgorithm, QgsProject


class EiaAlgorithm(QgsProcessingAlgorithm):
    LEVEL = "A"  # supervision level: A auto, B expert confirms, C locked

    def createInstance(self):
        return type(self)()

    def group(self):
        return "EIA models"

    def groupId(self):
        return "eia_models"

    def shortHelpString(self):
        return "Supervision level %s. %s" % (self.LEVEL, self.__doc__ or "")

    @staticmethod
    def project_dir(fallback):
        """Writable folder for the audit log: the QGIS project folder, else `fallback`,
        else a folder inside the QGIS profile (so an unsaved project still gets an audit trail)."""
        for cand in (QgsProject.instance().homePath(), fallback):
            if cand and os.path.isdir(cand) and os.access(cand, os.W_OK):
                return cand
        from qgis.core import QgsApplication

        d = os.path.join(QgsApplication.qgisSettingsDirPath(), "pcp_eia_audit")
        os.makedirs(d, exist_ok=True)
        return d
