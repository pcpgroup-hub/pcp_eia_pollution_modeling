# PCP-EIA Pollution Modeling (QGIS plugin, experimental)

Run pre-integrated environmental dispersion models inside QGIS for **Đánh giá tác động môi trường (EIA)**: air
(AERMOD, US EPA) and surface water (QUAL2Kw, Washington State Ecology). An expert, and the expert's own AI
assistant, prepare and run the models; the expert approves every step that runs a model; every run leaves an
audit trail. The plugin standardises how models are run and how maps are drawn. It does not certify compliance:
the expert stays responsible for the model and the conclusions.

Use it for any EIA work that needs a map: a project assessment, a permit file, a thesis on one discharge point.
The plugin produces no report template.

## What is in version 0.2.0

Algorithms are under *Processing Toolbox > PCP-EIA Pollution Modeling*.

**Air (full chain run in QGIS)**

| Algorithm | Does |
|---|---|
| Check model setup | Checks the model paths set in Processing settings |
| Make receptor grid | Receptor points around the sources, with a finer inner grid |
| Build AERMOD input | Writes `aermod.inp` from the source layer, receptors and AERMET files |
| Run AERMOD (level B) | Runs the AERMOD executable you installed, after the expert confirms |
| Import AERMOD plotfile as points | Reads a PLOTFILE into a point layer |
| Concentration contours | Contour polygons coloured by class (data, US EPA AQI or presentation style) |
| Scenario layout | Print layout as PNG: colour bar with threshold ticks, scale bar, coordinate system and model name |
| Run scenarios | One CSV row = one scenario = one map, one results row and one **method sheet** |
| Gauss screening, hourly screening | Quick screening estimates. Not AERMOD |
| Make test AERMET | Synthetic met files to try the workflow. Not for real files |

**Water**

| Algorithm | Does |
|---|---|
| QUAL2Kw: build Reach and Point Sources tables | CSV tables in the order of the official workbook sheets, from a river line and discharge points |
| QUAL2Kw: import results onto the river | Reads the "WQ Output" sheet of a workbook you have run and attaches it to the river line |

QUAL2Kw itself is run by the expert in the official Excel workbook (Windows). The plugin does not run it.
The workbook is a 1D, steady-state model without tides: tidal estuaries need another model.

**Coordinates**

| Algorithm | Does |
|---|---|
| VN-2000: reproject to the TM-3 zone of a province | 61 provinces with central meridians from Thông tư 973/2001/TT-TCĐC (2001 names; check the zone against the current rules) |

Use one CRS for a whole run. AERMOD needs metric coordinates (UTM or a VN-2000 TM-3 zone).

**Method sheet.** Next to each scenario map `run_scenarios` writes `<id>_phieu_phuong_phap.md`: plugin, QGIS and
AERMOD versions, met files, coordinate system, receptors, sources, colour classes, thresholds, assumptions, and
SHA-256 of the input files, with a line for the expert's sign-off. It records facts and judges nothing.

**Thresholds are yours.** The plugin ships no regulatory values. Threshold lines on the maps are typed by the
expert on each scenario row. Maps classified with the US EPA AQI breakpoints say so on the image.

Supervision levels: **A** runs freely; **B** the expert confirms in a dialog inside the QGIS window; **C** locked,
overriding needs a recorded reason. B and C refuse to run headless (`qgis_process`) or from a non-GUI channel, so an
AI cannot approve its own step. Audit log: `eia_audit.jsonl` next to the QGIS project, one JSON line per step with a
hash chain, SHA-256 of input and output files, approver and reason.

## Status and testing

* Tested on QGIS 4.3 (macOS, Intel) with AERMOD v26135 built from US EPA source, and the official QUAL2Kw v6 workbook
  (reading results only). Not tested on QGIS 3.x, Windows or Linux.
* 43 automated tests cover the pure-Python core: `python -m unittest discover -s pcp_eia_pollution_modeling/tests -t .`
  from the repository root. Anything that needs QGIS (Processing algorithms, print layout) was checked by hand.
* All example data in the tests and docs are invented. No client data ships with the plugin.
* The QUAL2Kw water map layout (river maps in the same style as the air maps) is planned, not done.

## Models are not bundled

The QGIS plugin repository does not accept binaries. Download the models yourself and set their paths in
*Settings > Options > Processing > Providers > PCP-EIA Pollution Modeling*:

* AERMOD: https://www.epa.gov/scram (US EPA SCRAM; version locked in the model card: 26135)
* QUAL2Kw: https://ecology.wa.gov/programs/eap/models.html (card locks v6.0)

## Model cards

`cards/*.json` declare inputs, outputs, limits, supervision levels and legal basis per model. Fields whose text
contains `verify` are not confirmed yet. See `docs/ADD_A_MODEL.md` for how to add a model.

## Licence

GPL-2.0-or-later (provisional, to be confirmed with the QGIS plugin repository maintainers). See `LICENSE`.

Author: Nguyễn Thị Thuý Nga. Developed within Team PCP (Công ty Dịch vụ Tài nguyên và Môi trường Phú Cường Phát).
Copyright © 2026 Nguyễn Thị Thuý Nga, Phú Cường Phát (Team PCP). Licence: GPL-2.0-or-later.

---

## Tóm tắt (tiếng Việt)

Plugin QGIS mã nguồn mở giúp người làm **Đánh giá tác động môi trường (EIA)**, cùng trợ lý AI của họ, chạy mô hình
quốc tế ngay trong QGIS: AERMOD (US EPA) cho không khí, QUAL2Kw cho nước mặt. Dùng được cho mọi dạng EIA cần bản đồ,
kể cả luận văn, luận án về một điểm xả thải. Plugin chuẩn hoá cách chạy và cách vẽ bản đồ (dải màu theo thang AQI của
US EPA, ngưỡng do chuyên gia nhập, hệ toạ độ VN-2000 theo tỉnh), ghi nhật ký kiểm toán và xuất phiếu phương pháp cho
từng bản đồ. Plugin không đóng gói mô hình và không kết luận mức tuân thủ; chuyên gia chịu trách nhiệm về mô hình và kết
luận của mình. Bản 0.2.0 đã thử trên QGIS 4.3 (macOS); phần bản đồ cho nước đang dự kiến.
