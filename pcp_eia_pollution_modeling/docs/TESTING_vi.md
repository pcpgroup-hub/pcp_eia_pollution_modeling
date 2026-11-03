# Cài đặt và kiểm thử bản 0.1.0 (tiếng Việt)

Bản này là khung. Các thuật toán đã viết nhưng chưa chạy trong QGIS lần nào, nên mục tiêu của lần thử đầu là tìm lỗi.

## 1. Cài đặt

1. Cài QGIS 3.40 LTR trở lên (hoặc QGIS 4).
2. QGIS > Plugins > Install from ZIP > chọn `pcp_eia_pollution_modeling.zip`. Plugin ở dạng thử nghiệm (experimental), nếu không thấy thì vào Plugins > Settings > bật "Show also experimental plugins".
3. Tải AERMOD (file chạy) từ EPA, QUAL2Kw từ Ecology. Không đặt vào thư mục plugin.
4. Settings > Options > Processing > Providers > PCP-EIA Pollution Modeling: điền đường dẫn AERMOD và QUAL2Kw.

## 2. Nối AI qua MCP (để Claude test)

Cài một trong hai plugin cầu MCP trên kho QGIS (QGIS MCP của nkarasiak, hoặc QGIS Agent MCP của Aaa2122) và làm theo
hướng dẫn trong trang plugin đó để nối với Claude. Sau khi nối, cho mình biết tên cầu và các công cụ nó liệt kê,
đặc biệt có công cụ chạy thuật toán Processing hay không (điểm kiểm trong bản kiến trúc).

## 3. Danh sách thử

| # | Việc | Kết quả mong đợi |
|---|---|---|
| 1 | Processing Toolbox có nhóm "PCP-EIA Pollution Modeling" với 3 thuật toán | Có |
| 2 | Chạy "Check model setup" | In đường dẫn AERMOD/QUAL2Kw và 3 thẻ |
| 3 | Chạy "Run AERMOD" với `aertest.inp` (EPA test case) trong cửa sổ QGIS | Hiện hộp thoại duyệt; bấm Yes thì chạy, bấm No thì từ chối |
| 4 | Cùng lệnh, bấm No | Thuật toán báo "expert did not approve" và KHÔNG chạy |
| 5 | Chạy bằng `qgis_process` trên dòng lệnh | Từ chối (không có cửa sổ) |
| 6 | Bỏ `DFAULT` khỏi MODELOPT trong bản sao của `.inp` | Hiện hộp thoại mức C đòi lý do |
| 7 | Sau lần chạy thành công: mở `eia_audit.jsonl` | Một dòng có approval, hash file vào/ra, kết quả |
| 8 | "Import AERMOD plotfile as points" với file `.PLT` từ test case, chọn CRS | Lớp điểm có cột conc, ave, grp; so giá trị với file gốc |
| 9 | AI gọi thuật toán qua cầu MCP | Hộp thoại duyệt vẫn hiện ở QGIS, AI không tự duyệt được |
| 10 | Chạy "Run AERMOD" trên máy macOS/Linux (nếu có) | Ghi lại có chạy được không |

Gặp lỗi: chép nội dung ở View > Panels > Log Messages (tab Python Error) gửi lại cho mình.

## 4. Điều mình chưa kiểm chứng

* Toàn bộ mã dùng QGIS API (thuật toán, provider, hộp thoại) chưa chạy trong QGIS 3.40 hay 4.
* Định dạng PLOTFILE đã theo tài liệu AERMOD nhưng chưa thử với tệp thật của EPA (các mẫu trong tests là mẫu viết tay).
* Việc `ProcessingConfig` và `QMetaType` hoạt động đúng trên QGIS 4.
