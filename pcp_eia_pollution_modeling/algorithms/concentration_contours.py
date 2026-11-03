# -*- coding: utf-8 -*-
import os
import re
import tempfile

import processing
from qgis.core import (Qgis, QgsFeature, QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsProcessingException,
                       QgsProcessingLayerPostProcessorInterface, QgsProcessingParameterFeatureSink,
                       QgsProcessingOutputString, QgsProcessingParameterBoolean, QgsProcessingParameterEnum, QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource, QgsProcessingUtils, QgsRendererRange, QgsVectorLayer)

from ..core.audit import AuditLog
from ..core import aqi as aqi_mod
from ..core.levels import fmt_vi, levels_from_limit, report_levels
from .base import EiaAlgorithm

_KEEP = []  # post-processors must outlive processAlgorithm
_SHOW = ["#2f6fd8", "#3fa3e8", "#35c4c8", "#4cc46a", "#9bd94a", "#e8e03c", "#f6b53a", "#f2802f", "#e8452c", "#b8142a"]  # blue-cyan-green-yellow-orange-red, as in dispersion-modelling presentation maps
_COLORS = ["#9b59d0", "#6f6fd6", "#5a8fc0", "#4fb0a8", "#58cf72", "#9be05a", "#f0e84f", "#f8b64f", "#f47c4f", "#ee3f3f"]  # purple-blue-green-yellow-red, as in common AERMOD plots


def ramp_colors(n, palette=None):
    """n colours interpolated along the palette (soft, continuous look)."""
    from qgis.PyQt.QtGui import QColor
    base = [QColor(c) for c in (palette or _COLORS)]
    out = []
    for i in range(n):
        t = (len(base) - 1) * (i / max(n - 1, 1))
        a = int(t)
        b = min(a + 1, len(base) - 1)
        f = t - a
        out.append(QColor(int(base[a].red() * (1 - f) + base[b].red() * f), int(base[a].green() * (1 - f) + base[b].green() * f),
                          int(base[a].blue() * (1 - f) + base[b].blue() * f)).name())
    return out


def parse_levels(text):
    """Levels from 'L1 L2 ...' (space or ';' separated, dot decimals), ascending, positive."""
    vals = [float(t) for t in re.split(r"[\s;]+", (text or "").strip()) if t]
    if any(v <= 0 for v in vals) or vals != sorted(set(vals)):
        raise ValueError("levels must be positive, ascending and distinct")
    return vals


class _Styler(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, levels, fill_all=True, soft=False, colors=None, names=None, basis="", show=False):
        super().__init__()
        self.show = show
        self.levels = levels
        self.fill_all = fill_all
        self.soft = soft
        self.colors = colors
        self.names = names
        self.basis = basis

    def postProcessLayer(self, layer, context, feedback):
        lv = self.levels
        ranges = []
        n_cls = len(lv) + 1
        soft_cols = ramp_colors(n_cls) if self.soft else None
        if self.colors:
            soft_cols = list(self.colors)
        show_cols = ramp_colors(len(lv), _SHOW) if self.show else None
        for i in range(len(lv) + 1):
            lo = -1e38 if i == 0 else lv[i - 1]
            hi = 1e38 if i == len(lv) else lv[i]
            if self.show:
                if i == 0:
                    sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_style": "no"})
                    label = "< %s µg/m³ (không tô)" % fmt_vi(lv[0])
                else:
                    sym = QgsFillSymbol.createSimple({"color": show_cols[i - 1], "outline_color": "70,40,40,150", "outline_width": "0.12"})
                    sym.setOpacity(0.74)
                    label = ("≥ %s µg/m³" % fmt_vi(lo)) if i == len(lv) else ("%s – %s µg/m³" % (fmt_vi(lo), fmt_vi(hi)))
            elif self.colors:
                col = self.colors[min(i, len(self.colors) - 1)]
                if i == 0 and not self.fill_all:
                    sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_style": "no"})  # 'Good' class left clear so the plume stands out
                else:
                    sym = QgsFillSymbol.createSimple({"color": col, "outline_color": "70,40,40,120", "outline_width": "0.12"})
                    sym.setOpacity(0.78)
                nm = self.names[min(i, len(self.names) - 1)]
                if i == 0:
                    rng = "< %s" % fmt_vi(lv[0])
                elif i == len(lv):
                    rng = "≥ %s" % fmt_vi(lo)
                else:
                    rng = "%s – %s" % (fmt_vi(lo), fmt_vi(hi))
                label = "%s (%s µg/m³)" % (nm, rng)
            elif i == 0 and not self.fill_all:
                sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_style": "no"})
                label = "< %s (không tô)" % fmt_vi(lv[0])
            elif i == 0:
                sym = QgsFillSymbol.createSimple({"color": soft_cols[0] if self.soft else _COLORS[0], "outline_style": "no"})
                sym.setOpacity(0.7)
                label = "< %s µg/m³" % fmt_vi(lv[0])
            else:
                ci = i if self.fill_all else i - 1
                col = soft_cols[i] if self.soft else _COLORS[min(ci, len(_COLORS) - 1)]
                sym = QgsFillSymbol.createSimple({"color": col, "outline_style": "no"})
                sym.setOpacity(0.72 if self.soft else 0.7)
                label = ("≥ %s µg/m³" % fmt_vi(lo)) if i == len(lv) else ("%s – %s µg/m³" % (fmt_vi(lo), fmt_vi(hi)))
                if self.soft and (i % 4 != 0 and i != len(lv)):
                    label = ""  # label every 4th class: the legend then reads as a continuous colour bar
            ranges.append(QgsRendererRange(lo, hi, sym, label))
        # classify on the band midpoint: c_min is stored as a float32 and can fall just below a non-round class edge (e.g. AQI 93.0202)
        layer.setRenderer(QgsGraduatedSymbolRenderer("(c_min + coalesce(c_max, c_min)) / 2", ranges))
        layer.setCustomProperty("pcpeia/aqi", "1" if self.colors else "0")
        layer.setCustomProperty("pcpeia/basis", self.basis)
        layer.setCustomProperty("pcpeia/names", "|".join(self.names or []))
        layer.triggerRepaint()


class ConcentrationContours(EiaAlgorithm):
    """Turn a concentration point layer (grid, any spacing) into filled contour polygons with a ready colour scale
    for screenshots. Levels in ug/m3, e.g. '1 2 5 10 20 50'; leave empty for 7 even steps up to the maximum."""

    LEVEL = "A"

    def name(self):
        return "concentration_contours"

    def displayName(self):
        return "Concentration contours (styled)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource("INPUT", "Concentration points",
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterField("FIELD", "Concentration field", parentLayerParameterName="INPUT",
                                                      type=QgsProcessingParameterField.DataType.Numeric, defaultValue="conc"))
        self.addParameter(QgsProcessingParameterString("LEVELS", "Levels (ug/m3, space separated; empty = automatic)", "", optional=True))
        self.addParameter(QgsProcessingParameterNumber("LIMIT", "Limit value for class levels (ug/m3, e.g. a QCVN value; used when Levels is empty)", QgsProcessingParameterNumber.Type.Double, 0, minValue=0, optional=True))
        self.addParameter(QgsProcessingParameterEnum("BASIS", "Class basis", ["Automatic (data, or the limit above)", "US EPA AQI categories", "Presentation map (blue to red, transparent below a threshold)"], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber("THRESHOLD_PCT", "Presentation map: do not colour below this % of the maximum", QgsProcessingParameterNumber.Type.Double, 5, minValue=0, maxValue=90))
        self.addParameter(QgsProcessingParameterBoolean("SMOOTH", "Smooth the contours (finer cubic resampling)", False))
        self.addParameter(QgsProcessingParameterEnum("AQI_POLLUTANT", "AQI pollutant and averaging time (when basis = EPA AQI)", aqi_mod.keys(), defaultValue=0))
        self.addParameter(QgsProcessingParameterString("BASIS_NAME", "Name of the standard shown in the legend (e.g. QCVN 05:2023/BTNMT)", "", optional=True))
        self.addParameter(QgsProcessingParameterBoolean("FILL_ALL", "Fill the whole computational domain (also the lowest class)", True))
        self.addParameter(QgsProcessingParameterBoolean("SOFT", "Soft look: many classes with a continuous colour ramp (used when Levels is empty)", False))
        self.addParameter(QgsProcessingParameterNumber("PIXEL", "Interpolation cell size (m)", QgsProcessingParameterNumber.Type.Double, 25, minValue=1))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Contours", type=Qgis.ProcessingSourceType.VectorPolygon))
        self.addOutput(QgsProcessingOutputString("LEVELS_USED", "Class levels used (ug/m3)"))
        self.addOutput(QgsProcessingOutputString("BASIS_TEXT", "Class basis text"))
        self.addOutput(QgsProcessingOutputString("COLORS_USED", "Colours used"))
        self.addOutput(QgsProcessingOutputString("NAMES_USED", "Class names used"))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, "INPUT", context)
        field = self.parameterAsString(parameters, "FIELD", context)
        idx = layer.fields().indexFromName(field)
        if layer is None or idx < 0:
            raise QgsProcessingException("Choose a point layer and a numeric field.")
        vals = [f[field] for f in layer.getFeatures() if f[field] is not None]
        try:
            mx = max(float(v) for v in vals)
        except (ValueError, TypeError):
            raise QgsProcessingException("The field has no numeric values.")
        if mx <= 0:
            raise QgsProcessingException("All concentrations are zero; nothing to draw.")
        try:
            levels = parse_levels(self.parameterAsString(parameters, "LEVELS", context))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        limit = self.parameterAsDouble(parameters, "LIMIT", context)
        soft = self.parameterAsBool(parameters, "SOFT", context)
        basis_i = self.parameterAsEnum(parameters, "BASIS", context)
        use_aqi = basis_i == 1
        show = basis_i == 2
        smooth = self.parameterAsBool(parameters, "SMOOTH", context) or show
        std = self.parameterAsString(parameters, "BASIS_NAME", context).strip()
        colors = names = None
        basis = ""
        if use_aqi:
            key = aqi_mod.keys()[self.parameterAsEnum(parameters, "AQI_POLLUTANT", context)]
            cls = aqi_mod.classes(key)
            levels, colors, names = cls["levels"], cls["colors"], cls["names"]
            basis = ("Ngưỡng AQI của US EPA, %s (%s). Phân loại áp lên nồng độ do dự án gây ra, chưa cộng nền; "
                     "không phải chỉ số AQI của khu vực." % (cls["label"], cls["source"]))
            if cls["warn"]:
                feedback.pushWarning(cls["warn"])
        elif show and not levels:
            thr = self.parameterAsDouble(parameters, "THRESHOLD_PCT", context)
            lo = mx * max(thr, 0.5) / 100.0
            levels = report_levels(lo, mx, 10)
            if len(levels) < 3:
                levels = [round(mx * k / 8.0, 3) for k in range(1, 8)]
            basis = ("Bản đồ trình diễn: chỉ tô vùng từ %s µg/m³ trở lên (%g%% giá trị cực đại); mức chia theo dữ liệu mô hình"
                     % (fmt_vi(levels[0]), thr))
        elif levels:
            basis = "Mức do chuyên gia nhập" + ("; bản đồ trình diễn" if show else "")
        else:
            limit = self.parameterAsDouble(parameters, "LIMIT", context)
            if soft:
                levels = sorted(set(float("%.3g" % (mx * k / 28.0)) for k in range(1, 28)))
                basis = "Mức chia đều theo dữ liệu mô hình (28 lớp)"
            elif limit > 0:
                lim_levels = [v for v in levels_from_limit(limit) if v < mx]
                if len(lim_levels) >= 6:
                    levels = lim_levels
                    basis = "Mức theo giới hạn %s µg/m³%s (chuyên gia nhập)" % (fmt_vi(limit), (" – " + std) if std else "")
                else:
                    mn0 = min(float(v) for v in vals)
                    levels = report_levels(mn0, mx, 10)
                    if limit < mx and limit not in levels:
                        levels = sorted(levels + [limit])
                    basis = "Mức chia theo dữ liệu (số tròn); giới hạn %s µg/m³%s cao hơn phần lớn giá trị nên không chia theo giới hạn" % (
                        fmt_vi(limit), (" – " + std) if std else "")
            else:
                mn0 = min(float(v) for v in vals)
                levels = report_levels(mn0, mx, 10) or [round(mx * k / 8.0, 3) for k in range(1, 8)]
                basis = "Mức chia theo dữ liệu mô hình (số tròn, khoảng 10 lớp)"
        limit = self.parameterAsDouble(parameters, "LIMIT", context)
        fill_all = self.parameterAsBool(parameters, "FILL_ALL", context) and not show
        td = tempfile.mkdtemp(prefix="pcpeia_")
        tif = os.path.join(td, "conc.tif")
        ext = layer.extent()
        pix = self.parameterAsDouble(parameters, "PIXEL", context)
        processing.run("native:tininterpolation", {
            "INTERPOLATION_DATA": "%s::~::0::~::%d::~::0" % (layer.id(), idx), "METHOD": 0, "PIXEL_SIZE": pix,
            "EXTENT": "%f,%f,%f,%f [%s]" % (ext.xMinimum(), ext.xMaximum(), ext.yMinimum(), ext.yMaximum(), layer.crs().authid()),
            "OUTPUT": tif}, context=context, feedback=None, is_child_algorithm=True)
        if smooth:
            tif2 = os.path.join(td, "conc_smooth.tif")
            processing.run("gdal:warpreproject", {"INPUT": tif, "RESAMPLING": 3, "TARGET_RESOLUTION": max(pix / 3.0, 1.0),
                                                  "DATA_TYPE": 0, "OUTPUT": tif2}, context=context, feedback=None, is_child_algorithm=True)
            tif = tif2
        res = processing.run("gdal:contour_polygon", {
            "INPUT": tif, "BAND": 1, "INTERVAL": max(levels[0], 1e-9), "OFFSET": 0, "FIELD_NAME_MIN": "c_min",
            "FIELD_NAME_MAX": "c_max", "CREATE_3D": False, "IGNORE_NODATA": False, "NODATA": None,
            "EXTRA": "-fl " + " ".join("%g" % v for v in levels),
            "OUTPUT": os.path.join(td, "contours.gpkg")}, context=context, feedback=None, is_child_algorithm=True)
        cl = QgsVectorLayer(res["OUTPUT"], "contours", "ogr")
        if not cl.isValid() or cl.featureCount() == 0:
            raise QgsProcessingException("No contour polygons were produced.")
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, cl.fields(), Qgis.WkbType.MultiPolygon, layer.crs())
        for f in cl.getFeatures():
            sink.addFeature(QgsFeature(f))
        if context.willLoadLayerOnCompletion(dest):
            st = _Styler(levels, fill_all, soft, colors, names, basis, show)
            _KEEP.append(st)
            context.layerToLoadOnCompletionDetails(dest).setPostProcessor(st)
        feedback.pushInfo("%d polygons, levels: %s ug/m3 (max %.2f)" % (cl.featureCount(), levels, mx))
        AuditLog(self.project_dir(td)).append(step="concentration_contours", level="A", model="none", card_version=None,
                                              parameters={"levels": levels, "limit": limit, "fill_all": fill_all, "pixel_m": pix, "max": mx})
        return {"OUTPUT": dest, "LEVELS_USED": " ".join("%g" % v for v in levels), "BASIS_TEXT": basis,
                "COLORS_USED": ",".join(colors or []), "NAMES_USED": "|".join(names or [])}
