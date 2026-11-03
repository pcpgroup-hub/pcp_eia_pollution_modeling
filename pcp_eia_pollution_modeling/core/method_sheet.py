# -*- coding: utf-8 -*-
"""Method sheet ("phiếu phương pháp") written next to every scenario map (pure Python, no QGIS).

One page of Markdown that says what the map is based on, so two maps can be compared on the same footing.
It records facts; it does not judge compliance. The expert stays responsible for the model and the dossier.
"""
import datetime
import hashlib
import os
import re


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
    except OSError:
        return ""
    return h.hexdigest()


def plugin_version(metadata_path):
    try:
        for line in open(metadata_path, encoding="utf-8"):
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def read_aermod_context(plt_path):
    """What can be read back from the AERMOD run folder that holds the plotfile (aermod.inp / aermod.out). Missing files give blanks."""
    d = os.path.dirname(os.path.abspath(plt_path))
    inp, out = os.path.join(d, "aermod.inp"), os.path.join(d, "aermod.out")
    ctx = {"folder": d, "inp": inp if os.path.isfile(inp) else "", "version": "", "aermet_version": "", "pollutant": "", "averaging": "",
           "surf": "", "prof": "", "year": "", "sources": [], "n_receptors": 0, "title": ""}
    if os.path.isfile(out):
        try:
            with open(out, encoding="utf-8", errors="replace") as fh:
                for ln in fh:   # the version banner sits after the echoed input, so scan until both are found
                    if not ctx["version"]:
                        m = re.search(r"AERMOD\s*-\s*VERSION\s+(\d+)", ln)
                        if m:
                            ctx["version"] = m.group(1)
                    if not ctx["aermet_version"]:
                        m = re.search(r"AERMET\s*-\s*VERSION\s+(\d+)", ln)
                        if m:
                            ctx["aermet_version"] = m.group(1)
                    if ctx["version"] and ctx["aermet_version"]:
                        break
        except OSError:
            pass
    if ctx["inp"]:
        try:
            with open(inp, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
        for ln in lines:
            t = ln.split()
            if len(t) < 2:
                continue
            k = t[0].upper()
            if k == "POLLUTID":
                ctx["pollutant"] = t[1]
            elif k == "AVERTIME":
                ctx["averaging"] = " ".join(t[1:])
            elif k == "SURFFILE":
                ctx["surf"] = t[1]
            elif k == "PROFFILE":
                ctx["prof"] = t[1]
            elif k == "SURFDATA" and len(t) >= 3:
                ctx["year"] = t[2]
            elif k == "TITLEONE":
                ctx["title"] = " ".join(t[1:])
            elif k == "DISCCART":
                ctx["n_receptors"] += 1
            elif k == "SRCPARAM" and len(t) >= 7:
                ctx["sources"].append({"id": t[1], "q": t[2], "h": t[3], "temp_k": t[4], "vel": t[5], "diam": t[6]})
    return ctx


def parse_thresholds(text):
    """'93=label; 40=label' -> [(93.0, 'label'), ...] (same separators as the map layout)."""
    out = []
    for part in re.split(r"[;\n]+", text or ""):
        part = part.strip()
        if not part:
            continue
        val, _, label = part.partition("=")
        try:
            out.append((float(val.strip().replace(",", ".")), label.strip()))
        except ValueError:
            continue
    return out


def _row(k, v):
    return "| %s | %s |" % (k, v if str(v).strip() else "(chưa có)")


def build_sheet(info):
    """info: dict of plain facts (see run_scenarios). Returns the Markdown text."""
    now = info.get("when") or datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    L = ["# Phiếu phương pháp: %s" % info.get("id", ""), "",
         "*%s*" % info.get("title", ""), "",
         "Phiếu này ghi lại cơ sở của bản đồ để so sánh các lần chạy trên cùng một chuẩn. Phiếu không đánh giá mức tuân thủ; "
         "chuyên gia chịu trách nhiệm về mô hình và kết luận của mình.", "",
         "## 1. Lần chạy", "", "| Mục | Nội dung |", "|---|---|",
         _row("Thời điểm lập phiếu", now),
         _row("Plugin PCP-EIA", info.get("plugin_version", "")),
         _row("QGIS", info.get("qgis_version", "")),
         _row("Chế độ", info.get("mode", "")), "",
         "## 2. Mô hình và khí tượng", "", "| Mục | Nội dung |", "|---|---|",
         _row("Mô hình", info.get("model", "")),
         _row("Phiên bản AERMOD / AERMET", "%s / %s" % (info.get("aermod_version", "") or "(chưa có)", info.get("aermet_version", "") or "(chưa có)")),
         _row("Chất ô nhiễm / thời gian trung bình", "%s / %s" % (info.get("pollutant", ""), info.get("averaging", ""))),
         _row("File khí tượng bề mặt / profile", "%s / %s" % (info.get("surf", ""), info.get("prof", ""))),
         _row("Năm số liệu khí tượng", info.get("year", "")), "",
         "## 3. Hệ toạ độ và lưới", "", "| Mục | Nội dung |", "|---|---|",
         _row("Hệ toạ độ", info.get("crs", "")),
         _row("Số điểm tiếp nhận", info.get("n_points", "")),
         _row("Ô nội suy bản đồ (m)", info.get("pixel", "")), ""]
    srcs = info.get("sources") or []
    L += ["## 4. Nguồn thải", ""]
    if srcs:
        L += ["| Nguồn | Phát thải (g/s) | Cao (m) | Nhiệt độ (K) | Vận tốc (m/s) | Đường kính (m) |", "|---|---|---|---|---|---|"]
        for s in srcs:
            L.append("| %s | %s | %s | %s | %s | %s |" % (s["id"], s["q"], s["h"], s["temp_k"], s["vel"], s["diam"]))
    else:
        L.append("(chưa đọc được tham số nguồn từ thư mục chạy AERMOD)")
    L += ["", "## 5. Cách trình bày", "", "| Mục | Nội dung |", "|---|---|",
          _row("Cơ sở chia mức", info.get("basis", "")),
          _row("Các mức màu (µg/m³)", info.get("levels", ""))]
    thr = info.get("thresholds") or []
    L += ["", "Ngưỡng vẽ trên bản đồ (do chuyên gia nhập; plugin không đóng sẵn giá trị quy chuẩn):", ""]
    if thr:
        L += ["| Giá trị (µg/m³) | Ghi chú của chuyên gia |", "|---|---|"] + ["| %s | %s |" % (v, lab) for v, lab in thr]
    else:
        L.append("(không có ngưỡng)")
    L += ["", "## 6. Kết quả", "", "| Mục | Nội dung |", "|---|---|",
          _row("Cực đại (µg/m³)", info.get("max", "")),
          _row("Vị trí cực đại", info.get("max_at", "")), "",
          "## 7. Giả định và giới hạn", ""]
    notes = [n.strip() for n in (info.get("notes") or "").split("|") if n.strip()]
    L += ["- %s" % n for n in notes] or ["- (chuyên gia chưa ghi)"]
    L += ["", "## 8. Truy vết", "", "| File | SHA-256 |", "|---|---|"]
    for name, h in info.get("hashes", []):
        L.append("| %s | `%s` |" % (name, h or "(không đọc được)"))
    L += ["", "## 9. Xác nhận", "", "Chuyên gia chịu trách nhiệm: ______________________    Ngày: ______________", ""]
    return "\n".join(L)
