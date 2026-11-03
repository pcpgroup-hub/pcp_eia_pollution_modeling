# Changelog

## 0.2.2
- Qt6 compliance: enums written fully qualified (`Type.Double`, `DataType.Numeric`, `GridStyle`, `AnnotationPosition`, `BorderSide`, `DisplayMode`, `ExportResult`, `StandardButton`), as the plugin repository's Qt6 check requires.

## 0.2.1
- Security scan fixes: QUAL2Kw workbook XML is read only after rejecting DTD/entity declarations; plugin unload logs a warning instead of silently ignoring errors.

## 0.2.0
- Air: scenario table runner (`run_scenarios`) with colour-band maps, threshold lines typed by the expert, US EPA AQI classes, print layout with coordinate system and model name, and a method sheet per scenario.
- Water: QUAL2Kw bridge: build Reach and Point Sources tables from QGIS layers; import "WQ Output" results onto the river line.
- VN-2000 TM-3 reprojection by province (central meridians from Thông tư 973/2001/TT-TCĐC).

## 0.1.0
- First skeleton: provider, approval gate, audit log, model cards, AERMOD run and plotfile import.
