# Quy tắc thể hiện hình phát tán ô nhiễm trong Đánh giá tác động môi trường (EIA) (cách trình bày phổ biến)

Các quy tắc dưới đây là thông lệ trình bày bản đồ đường đồng mức nồng độ trong Đánh giá tác động môi trường (EIA), ghi bằng lời; không sao chép hình, bố cục, tên hay nhãn hiệu của phần mềm nào. Plugin không liên kết với Lakes Environmental hay US EPA.

## 1. Quy tắc quan sát được
| Yếu tố | Quy tắc |
|---|---|
| Miền tính | Hình chữ nhật khoảng 22 km (Đông) × 18 km (Bắc), tâm gần nguồn thải; tô kín toàn miền |
| Lưới điểm | Lồng nhau: 200 m ở gần nguồn, 500 m ở xa, khoảng 2.000 điểm. Nội suy thô nên mép các lớp màu răng cưa, hình "ngôi sao" |
| Bản chất giá trị | Loại "cao nhất thứ nhất" (1st high): với mỗi điểm lấy giá trị lớn nhất trong cả năm theo giờ (1 h), theo ngày (24 h); riêng trung bình năm là trung bình cả năm. Vì vậy mọi hướng gió đều để lại một nan hoa, và hướng gió hiếm có giá trị thấp |
| Số lớp | Khoảng 10 lớp rời rạc (không liên tục) |
| Mức lớp | Cận dưới = giá trị nhỏ nhất của dữ liệu, cận trên = giá trị lớn nhất. Các mức giữa là số tròn (1, 1,5, 2, 3 … 9 × 10^k) cách nhau xấp xỉ theo cấp số nhân: dày ở giá trị thấp, thưa ở giá trị cao. Ví dụ: min; 300 400 500 600 700 1000 1500 2000; max |
| Bảng màu | Tím → xanh chàm → xanh lam xám → xanh lục → vàng lục → vàng → cam → đỏ (thấp → cao), bán trong suốt (khoảng 70%) để thấy nền |
| Nền | Bản đồ đường sá, sông hồ (có hình có, có hình không) |
| Điểm lớn nhất | Chấm đỏ nhỏ tại vị trí cực đại; giá trị và toạ độ ghi ở chú giải |
| Chú giải | Thanh màu đứng, nhãn tại cạnh các lớp, đơn vị µg/m³; dòng dọc ghi loại giá trị ("1st high 1-hr", "24-hr", "annual") |
| Khung bên phải | Số nguồn, số điểm nhận, loại kết quả, giá trị lớn nhất, tỷ lệ bản đồ, thước tỷ lệ |
| Trục | UTM Đông/Bắc (m), nhãn mỗi 2.000 m |

## 2. Công thức chung (áp dụng trong plugin)
- `1 h`: C(x,y) = max trên tập điều kiện khí tượng k của C_k(x,y)
- `24 h`: C(x,y) = hệ số trung bình × max_k C_k(x,y) (hệ số do chuyên gia đặt, ví dụ 0,4)
- `năm`: C(x,y) = Σ_k f_k C_k(x,y) (trung bình theo tần suất, hoa gió)
- Mức lớp: các số tròn gần nhất trên thang log giữa giá trị nhỏ nhất và lớn nhất, khoảng 10 lớp
- Màu lớp i trong N lớp: điểm thứ i/(N−1) trên bảng màu tím → đỏ, độ đục 0,7

Trong plugin, "tập điều kiện khí tượng" là một tập tổng hợp (hướng × tốc độ × cấp ổn định) thay cho số liệu từng giờ. Đây là mô hình sàng lọc đơn giản để xem giao diện, không phải kết quả AERMOD. Kết quả pháp lý vẫn phải chạy AERMOD với số liệu khí tượng thật (.SFC, .PFL).
