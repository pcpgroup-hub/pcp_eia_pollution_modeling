# -*- coding: utf-8 -*-
from qgis.core import Qgis, QgsMessageLog, QgsProcessingProvider

SETTING_AERMOD = "EIA_AERMOD_PATH"
SETTING_QUAL2KW = "EIA_QUAL2KW_PATH"


def get_model_path(key):
    """Path set by the user in Processing settings; '' when not set."""
    try:
        from processing.core.ProcessingConfig import ProcessingConfig

        value = ProcessingConfig.getSetting(key)
    except Exception:  # processing plugin missing or API change
        from qgis.core import QgsSettings

        value = QgsSettings().value("pcp_eia_pollution_modeling/" + key, "")
    return str(value or "")


class EiaProvider(QgsProcessingProvider):
    def id(self):
        return "pcpeia"

    def name(self):
        return "PCP-EIA Pollution Modeling"

    def longName(self):
        return "PCP-EIA Pollution Modeling (supervised environmental models)"

    def load(self):
        from processing.core.ProcessingConfig import ProcessingConfig, Setting

        ProcessingConfig.settingIcons[self.name()] = self.icon()
        ProcessingConfig.addSetting(Setting(self.name(), SETTING_AERMOD,
                                            "AERMOD executable (download from US EPA SCRAM)", "", valuetype=Setting.FILE))
        ProcessingConfig.addSetting(Setting(self.name(), SETTING_QUAL2KW,
                                            "QUAL2Kw executable or workbook (download from WA Ecology)", "", valuetype=Setting.FILE))
        ProcessingConfig.readSettings()
        self.refreshAlgorithms()
        return True

    def unload(self):
        try:
            from processing.core.ProcessingConfig import ProcessingConfig

            ProcessingConfig.removeSetting(SETTING_AERMOD)
            ProcessingConfig.removeSetting(SETTING_QUAL2KW)
        except Exception as exc:  # unloading must never raise; record why and carry on
            QgsMessageLog.logMessage("Could not remove settings on unload: %s" % exc, "PCP-EIA", Qgis.Warning)

    def loadAlgorithms(self):
        from .algorithms.check_setup import CheckModelSetup
        from .algorithms.run_aermod import RunAermod
        from .algorithms.import_plotfile import ImportAermodPlotfile
        from .algorithms.make_receptor_grid import MakeReceptorGrid
        from .algorithms.build_aermod_input import BuildAermodInput
        from .algorithms.gauss_screening import GaussScreening
        from .algorithms.hourly_screening import HourlyScreening
        from .algorithms.make_test_aermet import MakeTestAermet
        from .algorithms.concentration_contours import ConcentrationContours
        from .algorithms.scenario_layout import ScenarioLayout
        from .algorithms.run_scenarios import RunScenarios
        from .algorithms.qual2kw_bridge import Qual2kwBuildInput, Qual2kwImportResults
        from .algorithms.vn2000_reproject import Vn2000Reproject

        for cls in (CheckModelSetup, MakeReceptorGrid, GaussScreening, HourlyScreening, MakeTestAermet, ConcentrationContours, ScenarioLayout, RunScenarios, BuildAermodInput, RunAermod, ImportAermodPlotfile, Qual2kwBuildInput, Qual2kwImportResults, Vn2000Reproject):
            self.addAlgorithm(cls())
