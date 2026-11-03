# -*- coding: utf-8 -*-
import csv
import os
import re

import processing
from qgis.core import (Qgis, QgsProcessingException, QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber,
                       QgsProcessingParameterEnum, QgsProcessingParameterField, QgsProcessingOutputFolder,
                       QgsProcessingOutputFile, QgsProcessingParameterCrs, QgsProject, QgsVectorLayer)

from ..core.audit import AuditLog
from .base import EiaAlgorithm
from ..core import aqi as aqi_mod
from .concentration_contours import _Styler, parse_levels

aqi_keys = aqi_mod.keys()

_COLS_HELP = ("id, title, subtitle, emis_field, mode (env|rose|single|hourly|aermod), plt (AERMOD PLOTFILE path; with mode=aermod), thr (% of max below which nothing is coloured; basis=show), rose, dirs, speeds, stabs, avgf, wind, from, "
              "chat, kich_ban, mua, tb (labels for the results table), met (hourly CSV path; with mode=hourly), stat (max1h|max24h|mean), months, stab, amb, limit, levels, soft (0/1), basis (data|aqi|show), aqi (pm25_24h|pm10_24h|no2_1h|so2_1h|co_8h), basis_name, nguon (emission source, for the title: Nguồn thải – Thông số (chat) – Thời gian (tb)), model (name shown in the footer), thresholds ('value=label; value=label' threshold lines, ug/m3), info, outtype")


def _clean_id(text):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_") or "scenario"


class RunScenarios(EiaAlgorithm):
    """Run a table of scenarios one after another: for every row make the concentration field (simple Gauss
    screening), the styled contours and the print layout, and save PNG, parameter CSV and GeoPackage files in the
    output folder, plus one summary CSV. Columns (all optional except id): %s. Empty cells take defaults.
    The emission column is chosen per row (emis_field), so pollutant x treated/incident cases are just rows.
    Use 'Only these ids' to run a few rows at a time.""" % _COLS_HELP

    LEVEL = "A"

    def flags(self):
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading  # layouts render on the main thread

    def name(self):
        return "run_scenarios"

    def displayName(self):
        return "Run scenario table (batch maps)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("TABLE", "Scenario table (CSV or any table)", [Qgis.ProcessingSourceType.Vector]))
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Source / stack points", [Qgis.ProcessingSourceType.VectorPoint]))
        for key, label in (("HEIGHT", "Stack height field (m)"), ("TEMP", "Exit temperature field (deg C)"),
                           ("VEL", "Exit velocity field (m/s)"), ("DIAM", "Stack diameter field (m)")):
            self.addParameter(QgsProcessingParameterField(key, label, parentLayerParameterName="SOURCES", type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterFeatureSource("RECEPTORS", "Receptor points", [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterFeatureSource("BOUNDARY", "Project boundary", [Qgis.ProcessingSourceType.VectorPolygon, Qgis.ProcessingSourceType.VectorLine], optional=True))
        self.addParameter(QgsProcessingParameterCrs("CRS", "Model CRS (UTM, metres)"))
        self.addParameter(QgsProcessingParameterEnum("STYLE", "Layout style", ["Simple", "Framed"], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber("DPI", "Resolution (dpi)", QgsProcessingParameterNumber.Type.Integer, 150, minValue=72, maxValue=600))
        self.addParameter(QgsProcessingParameterNumber("PIXEL", "Interpolation cell size (m)", QgsProcessingParameterNumber.Type.Double, 100, minValue=1))
        from qgis.core import QgsProcessingParameterString
        self.addParameter(QgsProcessingParameterString("ONLY", "Only these ids (space or comma separated; empty = all rows)", "", optional=True))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTPUT_DIR", "Output folder"))
        self.addOutput(QgsProcessingOutputFile("SUMMARY", "Summary CSV"))

    @staticmethod
    def _val(feat, names, col, default=""):
        if col not in names:
            return default
        v = feat[col]
        if v is None or str(v).strip() == "" or str(v) == "NULL":
            return default
        return str(v).strip()

    def _write_sheet(self, path, sid, title, mode, g, gres, crs, vals, bp, cres, pixel, sources, receptors, png):
        """Method sheet next to the map (core/method_sheet.py). Reads the AERMOD run folder for version, met files and source parameters."""
        import datetime as _dt
        from qgis.core import Qgis
        from ..core import method_sheet as ms
        plt = g("plt") if mode == "aermod" else ""
        ctx = ms.read_aermod_context(plt) if plt else {}
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        hashes = []
        if plt:
            hashes.append((os.path.basename(plt), ms.sha256_of(plt)))
        if ctx.get("inp"):
            hashes.append(("aermod.inp", ms.sha256_of(ctx["inp"])))
        for f in (ctx.get("surf"), ctx.get("prof")):
            if f and os.path.isfile(os.path.join(ctx["folder"], f)):
                hashes.append((f, ms.sha256_of(os.path.join(ctx["folder"], f))))
        info = {
            "id": sid, "title": title, "mode": mode, "when": _dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "plugin_version": ms.plugin_version(os.path.join(here, "metadata.txt")), "qgis_version": Qgis.version(),
            "model": g("model", "AERMOD (US EPA)" if mode == "aermod" else "Gauss sàng lọc (không phải AERMOD)"),
            "aermod_version": ctx.get("version", ""), "aermet_version": ctx.get("aermet_version", ""), "pollutant": ctx.get("pollutant", "") or g("chat"), "averaging": ctx.get("averaging", "") or g("tb"),
            "surf": ctx.get("surf", ""), "prof": ctx.get("prof", ""), "year": ctx.get("year", ""),
            "crs": "%s (%s)" % (crs.description(), crs.authid()), "n_points": len(vals), "pixel": pixel,
            "sources": ctx.get("sources", []), "basis": cres.get("BASIS_TEXT", ""), "levels": cres.get("LEVELS_USED", ""),
            "thresholds": ms.parse_thresholds(g("thresholds")),
            "max": ("%.2f" % max(vals)) if vals else "", "max_at": ("%d E; %d N" % (round(bp.x()), round(bp.y()))) if bp else "",
            "notes": g("info"), "hashes": hashes}
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(ms.build_sheet(info))

    def processAlgorithm(self, parameters, context, feedback):
        table = self.parameterAsSource(parameters, "TABLE", context)
        names = [f.name() for f in table.fields()]
        if "id" not in names:
            raise QgsProcessingException("The table needs an 'id' column. Columns: %s" % _COLS_HELP)
        out_dir = self.parameterAsString(parameters, "OUTPUT_DIR", context)
        os.makedirs(out_dir, exist_ok=True)
        only = {t for t in re.split(r"[\s,;]+", self.parameterAsString(parameters, "ONLY", context).strip()) if t}
        rows = [f for f in table.getFeatures() if not only or str(f["id"]) in only]
        if not rows:
            raise QgsProcessingException("No rows to run (check the ids).")
        sources = self.parameterAsVectorLayer(parameters, "SOURCES", context)
        receptors = self.parameterAsVectorLayer(parameters, "RECEPTORS", context)
        boundary = self.parameterAsVectorLayer(parameters, "BOUNDARY", context)
        crs = self.parameterAsCrs(parameters, "CRS", context)
        fld = {k: self.parameterAsString(parameters, k, context) for k in ("HEIGHT", "TEMP", "VEL", "DIAM")}
        style = self.parameterAsEnum(parameters, "STYLE", context)
        dpi = self.parameterAsInt(parameters, "DPI", context)
        pixel = self.parameterAsDouble(parameters, "PIXEL", context)
        summary = []
        table_rows = {}
        zone = crs.authid()
        try:
            n = int(zone.split(":")[1])
            utm = "UTM%d%s" % (n % 100, "N" if 32600 < n < 32700 else "S") if 32600 < n < 32800 else "XY"
        except (IndexError, ValueError):
            utm = "XY"
        xcol, ycol = "X_%s_m" % utm, "Y_%s_m" % utm
        project = QgsProject.instance()
        for i, feat in enumerate(rows):
            if feedback.isCanceled():
                break
            sid = _clean_id(feat["id"])
            g = lambda col, d="": self._val(feat, names, col, d)
            feedback.pushInfo("[%d/%d] %s" % (i + 1, len(rows), sid))
            feedback.setProgress(100.0 * i / len(rows))
            rec = {"id": sid, "title": g("title", sid), "status": "ok", "error": ""}
            try:
                emis = g("emis_field")
                if g("mode", "env").lower() != "aermod" and (not emis or sources.fields().indexFromName(emis) < 0):
                    raise QgsProcessingException("emis_field '%s' is not a field of the source layer" % emis)
                mode = g("mode", "env").lower()
                if mode not in ("env", "rose", "single", "hourly", "aermod"):
                    raise QgsProcessingException("mode must be env, rose, single, hourly or aermod")
                if mode in ("env", "rose") and mode == "rose" and not g("rose"):
                    raise QgsProcessingException("mode 'rose' needs a 'rose' value (16 numbers)")
                pts_path = os.path.join(out_dir, sid + "_diem.gpkg")
                limit = float(g("limit", "0").replace(",", ".") or 0)
                if mode == "aermod":
                    if not g("plt") or not os.path.exists(g("plt")):
                        raise QgsProcessingException("mode 'aermod' needs a 'plt' column with the path of the AERMOD PLOTFILE")
                    gres = processing.run("pcpeia:import_aermod_plotfile", {"PLOTFILE": g("plt"), "CRS": crs, "OUTPUT": pts_path},
                                          context=context, feedback=None, is_child_algorithm=True)
                elif mode == "hourly":
                    if not g("met") or not os.path.exists(g("met")):
                        raise QgsProcessingException("mode 'hourly' needs a 'met' column with the path of the hourly CSV")
                    stat_i = ["max1h", "max24h", "mean"].index(g("stat", "max1h").lower())
                    gres = processing.run("pcpeia:hourly_screening", {
                        "SOURCES": sources, "EMIS": emis, "HEIGHT": fld["HEIGHT"], "TEMP": fld["TEMP"], "VEL": fld["VEL"],
                        "DIAM": fld["DIAM"], "RECEPTORS": receptors, "CRS": crs, "MET": g("met"), "STAT": stat_i,
                        "MONTHS": g("months"), "MINWS": 1.0, "LIMIT": ("%g" % limit) if limit > 0 else "", "OUTPUT": pts_path},
                        context=context, feedback=None, is_child_algorithm=True)
                else:
                  gres = processing.run("pcpeia:gauss_screening", {
                    "SOURCES": sources, "EMIS": emis, "HEIGHT": fld["HEIGHT"], "TEMP": fld["TEMP"], "VEL": fld["VEL"],
                    "DIAM": fld["DIAM"], "RECEPTORS": receptors, "CRS": crs,
                    "WIND": float(g("wind", "3").replace(",", ".")), "FROM": float(g("from", "225").replace(",", ".")),
                    "ROSE": g("rose") if mode in ("env", "rose") else "", "ENV": mode == "env",
                    "DIRS": g("dirs"), "SPEEDS": g("speeds", "1.5 3 5"), "STABS": g("stabs", "B D"),
                    "AVGF": float(g("avgf", "1").replace(",", ".")),
                    "STAB": "ABCDEF".index(g("stab", "D").upper()), "AMB": float(g("amb", "300").replace(",", ".")),
                    "LIMIT": ("%g" % limit) if limit > 0 else "", "OUTPUT": pts_path},
                    context=context, feedback=None, is_child_algorithm=True)
                soft = g("soft", "0") in ("1", "true", "yes", "True")
                lv_txt = g("levels")
                basis_i = {"aqi": 1, "show": 2, "trinh_dien": 2}.get(g("basis").lower(), 0)
                cres = processing.run("pcpeia:concentration_contours", {
                    "INPUT": gres["OUTPUT"], "FIELD": "conc", "LEVELS": lv_txt, "LIMIT": limit, "FILL_ALL": True,
                    "SOFT": soft, "PIXEL": pixel, "BASIS": basis_i, "THRESHOLD_PCT": float(g("thr", "5").replace(",", ".") or 5),
                    "SMOOTH": basis_i == 2,
                    "AQI_POLLUTANT": aqi_keys.index(g("aqi", aqi_keys[0])), "BASIS_NAME": g("basis_name"),
                    "OUTPUT": os.path.join(out_dir, sid + "_dong_muc.gpkg")},
                    context=context, feedback=None, is_child_algorithm=True)
                pl = QgsVectorLayer(pts_path, sid + "_diem", "ogr")
                cl = QgsVectorLayer(cres["OUTPUT"], sid + "_dong_muc", "ogr")
                if not pl.isValid() or not cl.isValid():
                    raise QgsProcessingException("Could not reopen the result files")
                _Styler(parse_levels(cres["LEVELS_USED"]), basis_i == 0, soft,
                        cres["COLORS_USED"].split(",") if cres["COLORS_USED"] else None,
                        cres["NAMES_USED"].split("|") if cres["NAMES_USED"] else None, cres["BASIS_TEXT"], basis_i == 2).postProcessLayer(cl, context, feedback)
                if g("nguon") and not g("title"):   # title: source - parameter - averaging time, as the expert's run is labelled
                    title_txt = "Nguồn thải: %s  –  Thông số: %s  –  Thời gian: %s" % (g("nguon"), g("chat", emis.upper()), g("tb", "1h"))
                else:
                    title_txt = g("title", sid)
                rec["title"] = title_txt
                png = os.path.join(out_dir, sid + ".png")
                lres = processing.run("pcpeia:scenario_layout", {
                    "CONTOURS": cl, "POINTS": pl, "FIELD": "conc", "SOURCES": sources, "BOUNDARY": boundary,
                    "TITLE": title_txt, "SUBTITLE": g("subtitle"), "INFO": g("info").replace("|", "\n"),
                    "STYLE": style, "THRESHOLDS": g("thresholds"),
                    "MODEL": g("model", "AERMOD (US EPA)" if mode == "aermod" else "Gauss sàng lọc (không phải AERMOD)"), "OUTTYPE": g("outtype", "Nồng độ"), "CAPTION": "", "LIMIT": limit, "DPI": dpi,
                    "OUTPUT": png}, context=context, feedback=None, is_child_algorithm=True)
                best = max((f for f in pl.getFeatures() if f["conc"] is not None), key=lambda f: float(f["conc"]), default=None)
                bp = best.geometry().asPoint() if best is not None else None
                vals = [float(f["conc"]) for f in pl.getFeatures() if f["conc"] is not None]
                tb_default = {"max1h": "1h", "max24h": "24h", "mean": "Trung bình năm"}.get(g("stat", "").lower(), "")
                table_rows[sid] = {
                    "Chat_o_nhiem": g("chat", emis.upper()), "Kich_ban": g("kich_ban", rec["title"]),
                    "Mua_Thoi_gian": g("mua", "Cả năm" if not g("months") else "Tháng " + g("months").replace(" ", ",")),
                    "Trung_binh": g("tb", tb_default), xcol: ("%d" % round(bp.x())) if bp else "", ycol: ("%d" % round(bp.y())) if bp else "",
                    "Nong_do_max_ug_m3": ("%.1f" % max(vals)) if vals else "",
                    "Thoi_diem_xay_ra": (gres.get("WHEN_MAX", "") or "") if mode == "hourly" else ""}
                sheet_path = os.path.join(out_dir, sid + "_phieu_phuong_phap.md")
                try:
                    self._write_sheet(sheet_path, sid, rec["title"], mode, g, gres, crs, vals, bp, cres, pixel, sources, receptors, png)
                except Exception as se:   # the sheet must never block the map
                    feedback.reportError("%s: method sheet not written (%s)" % (sid, se), False)
                    sheet_path = ""
                rec.update({"mode": mode, "emis_field": emis, "max": max(vals) if vals else "", "n_points": len(vals),
                            "levels": cres["LEVELS_USED"], "png": png, "table": lres.get("TABLE", ""), "sheet": sheet_path})
            except Exception as e:  # keep going: one bad row must not stop the batch
                lines = [l for l in str(e).splitlines() if l.strip()]
                rec.update({"status": "error", "error": (lines[-1] if lines else repr(e))})
                feedback.reportError("%s: %s" % (sid, rec["error"]), False)
            summary.append(rec)
        sp = os.path.join(out_dir, "tong_hop_kich_ban.csv")
        cols = ["id", "title", "status", "error", "mode", "emis_field", "max", "n_points", "levels", "png", "table", "sheet"]
        merged = {}
        if os.path.isfile(sp):  # running a few ids at a time keeps the earlier rows
            try:
                with open(sp, newline="", encoding="utf-8-sig") as fh:
                    for r in csv.DictReader(fh):
                        merged[r["id"]] = r
            except (OSError, KeyError, csv.Error):
                merged = {}
        for r in summary:
            merged[r["id"]] = r
        with open(sp, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(merged.values())
        # results table in the layout of an report appendix (one line per scenario), merged across chunked runs
        tp = os.path.join(out_dir, "bang_ket_qua.csv")
        tcols = ["Chat_o_nhiem", "Kich_ban", "Mua_Thoi_gian", "Trung_binh", xcol, ycol, "Nong_do_max_ug_m3", "Thoi_diem_xay_ra"]
        old = {}
        if os.path.isfile(tp):
            try:
                with open(tp, newline="", encoding="utf-8-sig") as fh:
                    for r in csv.DictReader(fh):
                        old[(r.get("Chat_o_nhiem"), r.get("Kich_ban"), r.get("Mua_Thoi_gian"), r.get("Trung_binh"))] = r
            except (OSError, csv.Error):
                old = {}
        for r in table_rows.values():
            old[(r["Chat_o_nhiem"], r["Kich_ban"], r["Mua_Thoi_gian"], r["Trung_binh"])] = r
        with open(tp, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=tcols, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(old.values())
        ok = sum(1 for r in summary if r["status"] == "ok")
        AuditLog(self.project_dir(out_dir)).append(
            step="run_scenarios", level="A", model="gauss_simple", card_version=None,
            parameters={"n_rows": len(summary), "n_ok": ok, "ids": [r["id"] for r in summary], "output_dir": out_dir,
                        "note": "screening only, not AERMOD"})
        feedback.pushInfo("%d of %d scenarios done. Summary: %s" % (ok, len(summary), sp))
        return {"SUMMARY": sp, "OUTPUT_DIR": out_dir}
