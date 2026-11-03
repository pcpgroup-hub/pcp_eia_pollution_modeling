# -*- coding: utf-8 -*-
import csv
import os
import re
import tempfile

from qgis.core import (Qgis, QgsFeature, QgsGeometry, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend,
                       QgsLayoutItemMap, QgsLayoutItemMapGrid, QgsLayoutItemScaleBar, QgsLayoutItemShape, QgsLayoutPoint, QgsFillSymbol, QgsLegendRenderer, QgsLegendStyle, QgsLayoutSize,
                       QgsField, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsPointXY, QgsVectorLayerSimpleLabeling, QgsPrintLayout, QgsProcessingException,
                       QgsProcessingParameterEnum, QgsProcessingParameterFeatureSource, QgsProcessingParameterField,
                       QgsProcessingParameterFileDestination, QgsProcessingParameterMapLayer,
                       QgsProcessingParameterNumber, QgsProcessingParameterString, QgsProject,
                       QgsRectangle, QgsSingleSymbolRenderer, QgsTextFormat, QgsUnitTypes, QgsVectorLayer)
from qgis.PyQt.QtCore import QMetaType, Qt
from qgis.PyQt.QtGui import QColor, QFont

from ..core.audit import AuditLog
from ..core.levels import fmt_vi
from .base import EiaAlgorithm


def _label(layout, text, x, y, w, h, size=9, bold=False, align=Qt.AlignmentFlag.AlignLeft):
    it = QgsLayoutItemLabel(layout)
    it.setText(text)
    f = QFont("Arial", int(round(size)))
    f.setBold(bold)
    tf = QgsTextFormat()
    tf.setFont(f)
    tf.setSize(size)
    it.setTextFormat(tf)
    it.setHAlign(align)
    it.setVAlign(Qt.AlignmentFlag.AlignTop)
    it.attemptMove(QgsLayoutPoint(x, y))
    it.attemptResize(QgsLayoutSize(w, h))
    layout.addLayoutItem(it)
    return it


def _rect(layout, x, y, w, h, fill=None, frame=True, alpha=255):
    """Rectangle; fill is a colour name or None; frame draws a thin black outline."""
    sh = QgsLayoutItemShape(layout)
    sh.setShapeType(QgsLayoutItemShape.Shape.Rectangle)
    props = {"color": "0,0,0,0", "outline_style": "no"}
    if fill:
        c = QColor(fill)
        c.setAlpha(alpha)
        props["color"] = "%d,%d,%d,%d" % (c.red(), c.green(), c.blue(), c.alpha())
    if frame:
        props.update({"outline_style": "solid", "outline_color": "0,0,0,255", "outline_width": "0.2"})
    sh.setSymbol(QgsFillSymbol.createSimple(props))
    sh.attemptMove(QgsLayoutPoint(x, y))
    sh.attemptResize(QgsLayoutSize(w, h))
    layout.addLayoutItem(sh)
    return sh


def _box(layout, x, y, w, h, caption, value="", vsize=9):
    """Framed information box with a small caption on top (a common layout for isopleth maps)."""
    _rect(layout, x, y, w, h)
    _label(layout, caption, x + 1.2, y + 0.6, w - 2, 3, 5)
    if value:
        _label(layout, value, x + 1.2, y + 3.6, w - 2, h - 4, vsize, True)


def _colorbar(layout, cl, x, top, bot, vmin, vmax, bar_w=8.0, thresholds=None):
    """Vertical colour bar with equal-height classes; labels at the class edges (bottom = minimum, top = maximum)."""
    rngs = list(cl.renderer().ranges()) if hasattr(cl.renderer(), "ranges") else []
    if not rngs:
        return
    hcls = (bot - top) / len(rngs)
    for i, r in enumerate(reversed(rngs)):
        sym = r.symbol()
        col = sym.color()
        al = int(255 * sym.opacity()) if col.alpha() > 0 else 0
        _rect(layout, x, top + i * hcls, bar_w, hcls, col.name(), True, al)
    first_clear = rngs[0].symbol().color().alpha() == 0
    labs = [("0" if first_clear else fmt_vi(vmin, 2))] + [fmt_vi(float("%.3g" % r.lowerValue())) for r in rngs[1:]] + [fmt_vi(vmax, 2)]
    step = max(1, -(-len(labs) // 14))  # at most about 14 labels
    last = len(labs) - 1
    for k, txt in enumerate(labs):
        keep = k == 0 or k == last or (k % step == 0 and last - k >= step / 2.0)
        if keep:
            _label(layout, txt, x + bar_w + 1.5, bot - k * hcls - 1.5, 20, 3, 7)
    for val, lab in (thresholds or []):   # threshold ticks: a black bar across the colour bar, label to the right of the class labels
        for j, r in enumerate(rngs):
            lo = vmin if r.lowerValue() < -1e30 else r.lowerValue()
            hi = vmax if r.upperValue() > 1e30 else r.upperValue()
            if lo <= val <= hi and hi > lo:
                yy = bot - (j + (val - lo) / (hi - lo)) * hcls
                _rect(layout, x - 1.8, yy - 0.3, bar_w + 3.6, 0.6, "#000000", False, 255)
                _label(layout, "◄ %s" % lab, x + bar_w + 11, yy - 1.6, 42, 9, 6, True)
                break
    if cl.customProperty("pcpeia/aqi") == "1":
        names = (cl.customProperty("pcpeia/names") or "").split("|")
        for i, nm in enumerate(names[:len(rngs)]):
            _label(layout, nm, x + bar_w + 13, bot - (i + 0.5) * hcls - 1.5, 42, 3, 6, True)


def _parse_thresholds(text):
    """'93=US EPA AQI: ranh Tốt / Trung bình; 40=Ngưỡng do chuyên gia nhập' -> [(93.0, 'US EPA ...'), (40.0, '...')]."""
    out = []
    for part in re.split(r"[;\n]+", text or ""):
        part = part.strip()
        if not part:
            continue
        v, _, lab = part.partition("=")
        val = float(v.strip().replace(",", "."))
        out.append((val, lab.strip() or "%s µg/m³" % fmt_vi(val)))
    return out


def _threshold_layers(pl, field, thr, crs):
    """One styled line layer per threshold (smoothed contour of the concentration field). First threshold: thick solid line,
    others: dashed. The layers are not added to the project; the caller keeps them alive while the layout is exported."""
    import processing
    idx = pl.fields().indexFromName(field)
    ext = pl.extent()
    pix = max(ext.width(), ext.height()) / 150.0
    td = tempfile.mkdtemp(prefix="pcpeia_thr_")
    tif = os.path.join(td, "t.tif")
    tif2 = os.path.join(td, "t2.tif")
    processing.run("native:tininterpolation", {
        "INTERPOLATION_DATA": "%s::~::0::~::%d::~::0" % (pl.source(), idx), "METHOD": 0, "PIXEL_SIZE": pix,
        "EXTENT": "%f,%f,%f,%f [%s]" % (ext.xMinimum(), ext.xMaximum(), ext.yMinimum(), ext.yMaximum(), crs.authid()),
        "OUTPUT": tif}, feedback=None)
    processing.run("gdal:warpreproject", {"INPUT": tif, "RESAMPLING": 3, "TARGET_RESOLUTION": max(pix / 3.0, 1.0),
                                          "DATA_TYPE": 0, "OUTPUT": tif2}, feedback=None)
    layers = []
    for i, (val, lab) in enumerate(thr):
        res = processing.run("gdal:contour", {"INPUT": tif2, "BAND": 1, "INTERVAL": 1e9, "FIELD_NAME": "conc",
                                              "EXTRA": "-fl %g" % val, "OUTPUT": os.path.join(td, "l%d.gpkg" % i)}, feedback=None)
        lyr = QgsVectorLayer(res["OUTPUT"], "thr%d" % i, "ogr")
        if not lyr.isValid() or lyr.featureCount() == 0:
            continue
        sym = QgsLineSymbol.createSimple({"color": "20,20,20", "width": "1.0" if i == 0 else "0.6",
                                          "line_style": "solid" if i == 0 else "dash", "capstyle": "round"})
        lyr.setRenderer(QgsSingleSymbolRenderer(sym))
        layers.append(lyr)
        # a single label per threshold: a point on the longest line part, so equal-level regions are not labelled again and again
        best = None
        for f in lyr.getFeatures():
            g = f.geometry()
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for pts in parts:
                geo = QgsGeometry.fromPolylineXY(pts)
                if best is None or geo.length() > best.length():
                    best = geo
        if best is not None:
            mp = best.interpolate(best.length() * 0.35)
            lab = QgsVectorLayer("Point?crs=%s&field=t:string" % crs.authid(), "thrlab%d" % i, "memory")
            ft = QgsFeature(lab.fields())
            ft.setGeometry(mp)
            ft.setAttribute("t", "%s µg/m³" % fmt_vi(val))
            lab.dataProvider().addFeatures([ft])
            lab.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "size": "0", "outline_style": "no", "color": "0,0,0,0"})))
            pal = QgsPalLayerSettings()
            pal.fieldName = "t"
            pal.placement = Qgis.LabelPlacement.OverPoint
            pal.displayAll = True   # threshold labels are always written, even if another label is near
            pal.priority = 10
            tf = QgsTextFormat()
            f2 = QFont("Arial")
            f2.setBold(True)
            tf.setFont(f2)
            tf.setSize(7.5)
            tf.buffer().setEnabled(True)
            tf.buffer().setSize(1.0)
            tf.buffer().setColor(QColor(255, 255, 255))
            pal.setFormat(tf)
            lab.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            lab.setLabelsEnabled(True)
            layers.append(lab)
    return layers


class ScenarioLayout(EiaAlgorithm):
    """One-scenario print map (A4 landscape): map with grid and scale bar, legend, information panel, red marker at
    the maximum. Uses the basemap/layers visible in the project. Writes a PNG and a CSV with the scenario parameters
    so the expert can paste both into the expert's report."""

    LEVEL = "A"

    def flags(self):
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading  # print layouts must render on the main thread

    def name(self):
        return "scenario_layout"

    def displayName(self):
        return "Make scenario layout (PNG + parameter table)"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMapLayer("CONTOURS", "Styled contour layer (from 'Concentration contours')"))
        self.addParameter(QgsProcessingParameterMapLayer("POINTS", "Concentration points (to locate the maximum)"))
        self.addParameter(QgsProcessingParameterString("FIELD", "Concentration field", "conc"))
        self.addParameter(QgsProcessingParameterFeatureSource("SOURCES", "Emission sources", [Qgis.ProcessingSourceType.VectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource("BOUNDARY", "Project boundary", [Qgis.ProcessingSourceType.VectorPolygon, Qgis.ProcessingSourceType.VectorLine], optional=True))
        self.addParameter(QgsProcessingParameterString("TITLE", "Title", "Kịch bản"))
        self.addParameter(QgsProcessingParameterString("SUBTITLE", "Subtitle (pollutant, averaging time, season)", "", optional=True))
        self.addParameter(QgsProcessingParameterString("INFO", "Extra information lines (one per line: meteorology, model, notes)", "", optional=True, multiLine=True))
        self.addParameter(QgsProcessingParameterEnum("STYLE", "Layout style", ["Simple: title, map, colour bar on the right", "Framed: with information boxes"], defaultValue=0))
        self.addParameter(QgsProcessingParameterString("OUTTYPE", "Output type shown in the frame", "Nồng độ"))
        self.addParameter(QgsProcessingParameterString("CAPTION", "Vertical caption beside the colour bar (empty = automatic)", "", optional=True))
        self.addParameter(QgsProcessingParameterNumber("LIMIT", "Limit value shown in the panel (ug/m3, optional)", QgsProcessingParameterNumber.Type.Double, 0, minValue=0, optional=True))
        self.addParameter(QgsProcessingParameterString("THRESHOLDS", "Threshold lines (ug/m3): 'value=label; value=label', e.g. 93=US EPA AQI: Tốt/Trung bình; 350=QCVN (expert enters)", "", optional=True))
        self.addParameter(QgsProcessingParameterString("MODEL", "Model name shown in the footer (e.g. AERMOD v26135, US EPA)", "", optional=True))
        self.addParameter(QgsProcessingParameterNumber("DPI", "Resolution (dpi)", QgsProcessingParameterNumber.Type.Integer, 200, minValue=72, maxValue=600))
        self.addParameter(QgsProcessingParameterFileDestination("OUTPUT", "Output PNG", "PNG files (*.png)"))

    def processAlgorithm(self, parameters, context, feedback):
        cl = self.parameterAsLayer(parameters, "CONTOURS", context)
        pl = self.parameterAsLayer(parameters, "POINTS", context)
        field = self.parameterAsString(parameters, "FIELD", context)
        if cl is None or pl is None or pl.fields().indexFromName(field) < 0:
            raise QgsProcessingException("Choose the contour layer, the point layer and a valid concentration field.")
        out = self.parameterAsFileOutput(parameters, "OUTPUT", context)
        crs = pl.crs()
        # maximum
        best = None
        n = 0
        mn = None
        for f in pl.getFeatures():
            v = f[field]
            if v is None:
                continue
            n += 1
            mn = float(v) if mn is None else min(mn, float(v))
            if best is None or float(v) > best[0]:
                best = (float(v), f.geometry().asPoint())
        if best is None:
            raise QgsProcessingException("The point layer has no values in the chosen field.")
        mxv, mxp = best
        e = pl.extent()
        tol = 1e-6 + 0.002 * max(e.width(), e.height())
        edge = max((float(f[field]) for f in pl.getFeatures() if f[field] is not None and (
            abs(f.geometry().asPoint().x() - e.xMinimum()) < tol or abs(f.geometry().asPoint().x() - e.xMaximum()) < tol or
            abs(f.geometry().asPoint().y() - e.yMinimum()) < tol or abs(f.geometry().asPoint().y() - e.yMaximum()) < tol)), default=0.0)
        if mxv > 0 and edge > 0.05 * mxv:
            feedback.pushWarning("The concentration at the grid edge is %.0f%% of the maximum: the plume is cut off. "
                                 "Enlarge the receptor grid (radius), especially downwind." % (100.0 * edge / mxv))
        # temporary marker layer
        ml = QgsVectorLayer("Point?crs=%s" % crs.authid(), "max", "memory")
        ml.dataProvider().addAttributes([QgsField("lbl", QMetaType.Type.QString)])
        ml.updateFields()
        mf = QgsFeature(ml.fields())
        mf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(mxp)))
        mf.setAttribute("lbl", "Max %s µg/m³" % fmt_vi(mxv, 2))
        ml.dataProvider().addFeatures([mf])
        ml.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": "#e00000", "outline_color": "#ffffff", "outline_width": "0.4", "size": "3.4"})))
        pal = QgsPalLayerSettings()
        pal.fieldName = "lbl"
        pal.placement = Qgis.LabelPlacement.OverPoint
        pal.priority = 2
        pal.xOffset, pal.yOffset = 4.0, -4.0
        tf = QgsTextFormat()
        tf.setSize(9)
        tf.buffer().setEnabled(True)
        tf.buffer().setColor(QColor(255, 255, 255))
        pal.setFormat(tf)
        ml.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        ml.setLabelsEnabled(True)
        project = QgsProject.instance()
        project.addMapLayer(ml, False)
        try:
            layers = [ml]
            keep_alive = []
            for nm in ("SOURCES", "BOUNDARY"):
                lyr = self.parameterAsVectorLayer(parameters, nm, context)
                if lyr is not None:
                    lyr = lyr.clone()  # own style for the print map; the project layer keeps its look
                    if nm == "BOUNDARY":
                        sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "255,215,0", "outline_width": "0.7", "outline_style": "dash"}) if lyr.geometryType() == 2 else None
                        if sym is not None:
                            lyr.setRenderer(QgsSingleSymbolRenderer(sym))
                    else:
                        lyr.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
                            {"name": "triangle", "color": "#e00000", "outline_color": "#ffffff", "outline_width": "0.4", "size": "3.6"})))
                    keep_alive.append(lyr)
                    layers.append(lyr)
            thr = _parse_thresholds(self.parameterAsString(parameters, "THRESHOLDS", context))
            thr_layers = _threshold_layers(pl, field, thr, crs) if thr else []
            layers[1:1] = thr_layers
            layers.append(cl)
            seen = {l.id() for l in layers}
            for node in project.layerTreeRoot().findLayers():
                lyr = node.layer()
                if lyr is not None and node.isVisible() and lyr.id() not in seen and lyr.crs().isValid() is not None:
                    layers.append(lyr)
                    seen.add(lyr.id())
            # keep the contour layer above the basemap, below the vector overlays
            layout = QgsPrintLayout(project)
            layout.initializeDefaults()
            pg = layout.pageCollection().page(0)
            pg.setPageSize(QgsLayoutSize(297, 210))
            style = self.parameterAsEnum(parameters, "STYLE", context)
            mapw, maph, mx = (212.0, 167.0, 12.0) if style == 0 else (186.0, 172.0, 25.0)
            ext = cl.extent()
            if not ext.isFinite() or ext.isEmpty():
                ext = pl.extent()
            ext.scale(1.04)
            cx, cy = ext.center().x(), ext.center().y()
            ratio = mapw / maph
            w, h = ext.width(), ext.height()
            if w / h > ratio:
                h = w / ratio
            else:
                w = h * ratio
            ext = QgsRectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            mp = QgsLayoutItemMap(layout)
            mp.setCrs(crs)
            mp.attemptMove(QgsLayoutPoint(mx, 24))
            mp.attemptResize(QgsLayoutSize(mapw, maph))
            mp.setLayers(layers)
            mp.setKeepLayerSet(True)
            mp.setExtent(ext)
            mp.setFrameEnabled(True)
            grid = QgsLayoutItemMapGrid("grid", mp)
            interval = max(100, round(w / 5, -2))
            grid.setIntervalX(interval)
            grid.setIntervalY(interval)
            grid.setStyle(QgsLayoutItemMapGrid.GridStyle.FrameAnnotationsOnly)
            grid.setAnnotationEnabled(True)
            grid.setAnnotationPrecision(0)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.OutsideMapFrame, QgsLayoutItemMapGrid.BorderSide.Left)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.OutsideMapFrame, QgsLayoutItemMapGrid.BorderSide.Bottom)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.InsideMapFrame, QgsLayoutItemMapGrid.BorderSide.Right)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.InsideMapFrame, QgsLayoutItemMapGrid.BorderSide.Top)
            grid.setAnnotationDisplay(QgsLayoutItemMapGrid.DisplayMode.HideAll, QgsLayoutItemMapGrid.BorderSide.Right)
            grid.setAnnotationDisplay(QgsLayoutItemMapGrid.DisplayMode.HideAll, QgsLayoutItemMapGrid.BorderSide.Top)
            af = QgsTextFormat()
            af.setSize(6)
            grid.setAnnotationTextFormat(af)
            mp.grids().addGrid(grid)
            layout.addLayoutItem(mp)
            title = self.parameterAsString(parameters, "TITLE", context)
            sub = self.parameterAsString(parameters, "SUBTITLE", context)
            outtype = self.parameterAsString(parameters, "OUTTYPE", context)
            caption = self.parameterAsString(parameters, "CAPTION", context).strip()
            limit = self.parameterAsDouble(parameters, "LIMIT", context)
            extra = [l for l in self.parameterAsString(parameters, "INFO", context).splitlines() if l.strip()]
            basis_txt = cl.customProperty("pcpeia/basis") or ""
            if basis_txt:
                extra = ["Cơ sở chia mức: " + basis_txt] + extra
            nsrc = 0
            src = self.parameterAsSource(parameters, "SOURCES", context)
            if src is not None:
                nsrc = src.featureCount()
            if style == 0:
                scale_txt = "1:%s" % ("{:,.0f}".format(mp.scale()).replace(",", "."))
                rows = [("Số nguồn thải", str(nsrc)), ("Số điểm tính", str(n)), ("Loại kết quả", outtype),
                        ("Giá trị nhỏ nhất", "%s µg/m³" % fmt_vi(mn if mn is not None else 0, 2)),
                        ("Giá trị lớn nhất", "%s µg/m³" % fmt_vi(mxv, 2)),
                        ("Vị trí lớn nhất", "%s E; %s N" % (fmt_vi(mxp.x(), 0), fmt_vi(mxp.y(), 0))),
                        ("Hệ toạ độ", crs.authid()), ("Tỷ lệ bản đồ", scale_txt)]
                if limit > 0:
                    rows.append(("Giới hạn", "%s µg/m³" % fmt_vi(limit)))
                    rows.append(("Max / giới hạn", "%s %%" % fmt_vi(100.0 * mxv / limit, 1)))
                _label(layout, title, 10, 5, 277, 9, 15 if len(title) <= 62 else (12 if len(title) <= 85 else 10), True, Qt.AlignmentFlag.AlignHCenter)
                if sub:
                    _label(layout, sub, 10, 14, 277, 6, 8, False, Qt.AlignmentFlag.AlignHCenter)
                bx = mx + mapw + 8
                _label(layout, "µg/m³", bx - 1, 24.5, 20, 4, 8, True)
                _colorbar(layout, cl, bx, 31.0, 185.0, mn if mn is not None else 0.0, mxv, thresholds=thr)
                sb = QgsLayoutItemScaleBar(layout)
                sb.setLinkedMap(mp)
                sb.setUnits(Qgis.DistanceUnit.Meters)
                sb.setNumberOfSegments(2)
                sb.setNumberOfSegmentsLeft(0)
                sb.setUnitsPerSegment(max(500, round(w / 8, -3)))
                sb.setUnitLabel("m")
                sbf = QgsTextFormat()
                sbf.setSize(7)
                sb.setTextFormat(sbf)
                sb.setBackgroundEnabled(True)
                sb.setBackgroundColor(QColor(255, 255, 255, 220))
                sb.attemptMove(QgsLayoutPoint(mx + 3, 179))
                layout.addLayoutItem(sb)
                model = self.parameterAsString(parameters, "MODEL", context).strip()
                crs_txt = "%s (%s)" % (crs.description() or "", crs.authid())
                foot1 = "Max: %s µg/m³ tại (%s E; %s N)  |  %d điểm tính" % (fmt_vi(mxv, 2), fmt_vi(mxp.x(), 0), fmt_vi(mxp.y(), 0), n)
                if limit > 0:
                    foot1 += "  |  Giới hạn %s µg/m³" % fmt_vi(limit)
                foot2 = "Hệ toạ độ: %s  |  Tỷ lệ %s" % (crs_txt, scale_txt) + (("  |  Mô hình: " + model) if model else "")
                _label(layout, foot1, mx, 196.5, 277, 4, 7)
                _label(layout, foot2, mx, 200.5, 277, 4, 7, True)
                if extra:
                    _label(layout, "  |  ".join(extra), mx, 205, 277, 4, 6)
                _label(layout, "↑ B", mx + mapw - 12, 26, 10, 6, 9, True, Qt.AlignmentFlag.AlignRight)
            else:
                # outer frame and title box
                _rect(layout, 5, 4, 287, 203)
                _box(layout, 5, 4, 205, 16, "TIÊU ĐỀ", title, 11)
                if sub:
                    _label(layout, sub, 7, 13.5, 200, 6, 7)
                # axis titles
                _label(layout, "Toạ độ Đông (UTM) [m]", 25, 200, mapw, 4, 7, False, Qt.AlignmentFlag.AlignHCenter)
                ay = _label(layout, "Toạ độ Bắc (UTM) [m]", 7 + 2 - maph / 2.0, 24 + maph / 2.0 - 2, maph, 4, 7, False, Qt.AlignmentFlag.AlignHCenter)
                ay.setItemRotation(-90)
                # right-hand column: colour bar (classes read from the contour layer's renderer)
                rx, rw = 213, 77
                _rect(layout, rx, 4, rw, 108)
                _label(layout, "µg/m³", rx + 2, 5.5, 20, 4, 7, True)
                rngs = list(cl.renderer().ranges()) if hasattr(cl.renderer(), "ranges") else []
                top, bot = 12.0, 106.0
                if rngs:
                    hcls = (bot - top) / len(rngs)
                    edges = [r.lowerValue() for r in rngs[1:]]
                    for i, r in enumerate(reversed(rngs)):
                        sym = r.symbol()
                        col = sym.color()
                        al = int(255 * sym.opacity()) if col.alpha() > 0 else 0
                        _rect(layout, rx + 3, top + i * hcls, 7, hcls, col.name(), True, al)
                    labs = [("%s" % fmt_vi(mn if mn is not None else 0, 2))] + [fmt_vi(v) for v in edges] + [fmt_vi(mxv, 2)]
                    for k, txt in enumerate(labs):   # k = 0 is the bottom edge
                        yy = bot - k * hcls
                        _label(layout, txt, rx + 11, yy - 1.5, 14, 3, 6)
                cap = caption or "Giá trị lớn nhất tại điểm nhận | Max: %s µg/m³ tại (%s; %s)" % (
                    fmt_vi(mxv, 2), fmt_vi(mxp.x(), 0), fmt_vi(mxp.y(), 0))
                vlen = bot - top + 2
                vc = _label(layout, cap, rx + 27 + 2 - vlen / 2.0, top + vlen / 2.0 - 2, vlen, 4, 5, False, Qt.AlignmentFlag.AlignHCenter)
                vc.setItemRotation(-90)
                _box(layout, rx, 112, rw, 9, "NGUỒN THẢI", str(nsrc))
                _box(layout, rx, 121, rw, 9, "ĐIỂM NHẬN", str(n))
                _box(layout, rx, 130, rw, 9, "LOẠI KẾT QUẢ", outtype)
                _box(layout, rx, 139, rw, 11, "GIÁ TRỊ LỚN NHẤT", "%s µg/m³" % fmt_vi(mxv, 2), 10)
                _box(layout, rx, 150, rw, 17, "TỶ LỆ BẢN ĐỒ", "")
                scale_txt = "1:%s" % ("{:,.0f}".format(mp.scale()).replace(",", "."))
                _label(layout, scale_txt, rx + rw - 28, 150.6, 26, 3.5, 6, False, Qt.AlignmentFlag.AlignRight)
                sb = QgsLayoutItemScaleBar(layout)
                sb.setLinkedMap(mp)
                sb.setUnits(Qgis.DistanceUnit.Meters)
                sb.setNumberOfSegments(2)
                sb.setNumberOfSegmentsLeft(0)
                sb.setUnitsPerSegment(max(500, round(w / 8, -3)))
                sb.setUnitLabel("m")
                sbf = QgsTextFormat()
                sbf.setSize(6)
                sb.setTextFormat(sbf)
                sb.attemptMove(QgsLayoutPoint(rx + 2, 155))
                layout.addLayoutItem(sb)
                rows = [("Số nguồn thải", str(nsrc)), ("Số điểm tính", str(n)), ("Loại kết quả", outtype),
                        ("Giá trị nhỏ nhất", "%s µg/m³" % fmt_vi(mn if mn is not None else 0, 2)),
                        ("Giá trị lớn nhất", "%s µg/m³" % fmt_vi(mxv, 2)),
                        ("Vị trí lớn nhất", "%s E; %s N" % (fmt_vi(mxp.x(), 0), fmt_vi(mxp.y(), 0))),
                        ("Hệ toạ độ", crs.authid()), ("Tỷ lệ bản đồ", scale_txt)]
                note = []
                if limit > 0:
                    rows.append(("Giới hạn", "%s µg/m³" % fmt_vi(limit)))
                    rows.append(("Max / giới hạn", "%s %%" % fmt_vi(100.0 * mxv / limit, 1)))
                    note.append("Giới hạn: %s µg/m³ (max = %s%%)" % (fmt_vi(limit), fmt_vi(100.0 * mxv / limit, 1)))
                _box(layout, rx, 167, rw, 40, "GHI CHÚ", "")
                _label(layout, "\n".join(note + extra), rx + 1.2, 170.5, rw - 2, 34, 6)
                _label(layout, "PCP-EIA Pollution Modeling (QGIS)", 7, 203.5, 80, 3, 5)
                _label(layout, "↑ B", mapw + 25 - 14, 26, 12, 6, 9, True, Qt.AlignmentFlag.AlignRight)
            exp = QgsLayoutExporter(layout)
            s = QgsLayoutExporter.ImageExportSettings()
            s.dpi = self.parameterAsInt(parameters, "DPI", context)
            if exp.exportToImage(out, s) != QgsLayoutExporter.ExportResult.Success:
                raise QgsProcessingException("Could not export the PNG to %s" % out)
        finally:
            project.removeMapLayer(ml.id())
        csv_path = os.path.splitext(out)[0] + "_thong_so.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.writer(fh)
            wr.writerow(["Thông số", "Giá trị"])
            wr.writerow(["Tiêu đề", title])
            wr.writerow(["Mô tả", sub])
            for k, v in rows:
                wr.writerow([k, v])
            if basis_txt:
                wr.writerow(["Cơ sở chia mức", basis_txt])
            for l in extra:
                if not l.startswith("Cơ sở chia mức"):
                    wr.writerow(["Ghi chú", l])
        AuditLog(self.project_dir(os.path.dirname(out) or ".")).append(
            step="scenario_layout", level="A", model="none", card_version=None,
            parameters={"title": title, "max": mxv, "n_points": n, "png": out, "csv": csv_path})
        feedback.pushInfo("PNG: %s | CSV: %s | max %.3f at %.0f, %.0f" % (out, csv_path, mxv, mxp.x(), mxp.y()))
        return {"OUTPUT": out, "TABLE": csv_path}

