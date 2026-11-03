# -*- coding: utf-8 -*-
import os
import subprocess

from qgis.core import (Qgis, QgsProcessingException, QgsProcessingOutputBoolean, QgsProcessingOutputFile,
                       QgsProcessingParameterFile, QgsProcessingParameterNumber, QgsProcessingParameterString)

from ..core import aermod_io, approval, cards
from ..core.audit import AuditLog
from ..provider import SETTING_AERMOD, get_model_path
from .base import EiaAlgorithm


class RunAermod(EiaAlgorithm):
    """Run AERMOD on a control file. The expert confirms in the QGIS window before it starts (level B);
    a control file without DFAULT needs a recorded reason (level C)."""

    LEVEL = "B"

    def name(self):
        return "run_aermod"

    def displayName(self):
        return "Run AERMOD (needs expert approval)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("INPUT", "AERMOD control file (.inp)",
                                                     behavior=Qgis.ProcessingFileParameterBehavior.File, extension="inp"))
        self.addParameter(QgsProcessingParameterString("OUTPUT_NAME", "Output file name", defaultValue="aermod.out"))
        self.addParameter(QgsProcessingParameterNumber("TIMEOUT", "Time limit (minutes)",
                                                       type=Qgis.ProcessingNumberParameterType.Integer, defaultValue=120, minValue=1))
        self.addOutput(QgsProcessingOutputFile("OUTPUT_FILE", "AERMOD output"))
        self.addOutput(QgsProcessingOutputBoolean("SUCCESS", "Run finished without error"))

    def prepareAlgorithm(self, parameters, context, feedback):
        # Runs on the main thread: the only place the approval dialog may be shown.
        self._inp = self.parameterAsFile(parameters, "INPUT", context)
        self._out_name = self.parameterAsString(parameters, "OUTPUT_NAME", context) or "aermod.out"
        self._timeout = self.parameterAsInt(parameters, "TIMEOUT", context) * 60
        self._exe = get_model_path(SETTING_AERMOD)
        if not self._exe or not os.path.isfile(self._exe):
            raise QgsProcessingException("AERMOD executable not set. Set it in Settings > Options > Processing > Providers > PCP-EIA Pollution Modeling.")
        if not os.path.isfile(self._inp):
            raise QgsProcessingException("Control file not found: %s" % self._inp)
        self._dir = os.path.dirname(os.path.abspath(self._inp))
        with open(self._inp, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        card = cards.load_card("aermod")
        self._card_version = card.get("_card_version")
        self._approvals = []
        dfault = aermod_io.uses_dfault(text)
        try:
            if not dfault:
                self._approvals.append(approval.require(
                    "C", "DFAULT missing",
                    "The control file has no DFAULT on MODELOPT. Without it the run is not a regulatory default run.\nFile: %s" % self._inp))
            self._approvals.append(approval.require(
                "B", "Run AERMOD",
                "Run %s\nControl file: %s\nWorking folder: %s\nDFAULT: %s\nModel card aermod v%s" % (
                    self._exe, self._inp, self._dir, "yes" if dfault else "NO (override recorded)", self._card_version)))
        except approval.ApprovalRefused as exc:
            raise QgsProcessingException(str(exc))
        self._audit_dir = self.project_dir(self._dir)
        self._files = [self._inp] + aermod_io.referenced_files(text, self._dir)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        out_path = os.path.join(self._dir, self._out_name)
        feedback.pushInfo("Running AERMOD in %s" % self._dir)
        try:
            # Bandit B603: argument list, no shell, absolute path of the executable the user set in
            # Processing settings, control file chosen by the user and approved in the QGIS window.
            proc = subprocess.run([os.path.abspath(self._exe), os.path.basename(self._inp), self._out_name],  # nosec B603
                                  cwd=self._dir, capture_output=True, text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise QgsProcessingException("AERMOD exceeded the time limit")
        ok = proc.returncode == 0 and os.path.isfile(out_path)
        if ok:
            with open(out_path, encoding="utf-8", errors="replace") as fh:
                ok = not aermod_io.run_failed(fh.read())
        feedback.pushInfo("AERMOD finished, success=%s" % ok)
        AuditLog(self._audit_dir).append(
            step="run_aermod", level="B", model="aermod", card_version=self._card_version,
            parameters={"exe": self._exe, "inp": self._inp, "out": out_path, "timeout_s": self._timeout},
            approval=self._approvals, files=self._files + [out_path], result={"returncode": proc.returncode, "success": ok})
        if not ok:
            raise QgsProcessingException("AERMOD run failed; see %s" % out_path)
        return {"OUTPUT_FILE": out_path, "SUCCESS": ok}
