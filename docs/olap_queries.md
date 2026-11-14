# OLAP và Dashboard

Phụ trách: P2. Các thao tác OLAP chạy trên schema `olap` (view phẳng và materialized view) xây từ star schema trong [dw_design.md](dw_design.md).

Tạo view sau khi chạy ETL bằng `python -m src.olap.build`. Các lần ETL sau chỉ cần `python -m src.olap.build --refresh`.

## 1. Lớp dữ liệu OLAP (`src/olap/views`)

| Đối tượng | Grain | Mục đích |
|---|---|---|
| `olap.v_sales` | 1 sản phẩm trong 1 đơn | `fact_sales` nối `dim_date`, `dim_product`, `dim_seller`, `dim_customer`, `dim_order_status` và 2 lần `dim_geography` (người bán, khách) |
| `olap.v_fulfillment` | 1 đơn | `fact_order_fulfillment` + khách/địa lý + **tuyến** (bang người bán → bang khách), **danh mục chính**, `distance_km` |
| `olap.v_payment`, `olap.v_review` | 1 lần thanh toán / 1 review | Fact tương ứng + ngày + địa lý khách |
| `olap.v_order_main_item` | 1 đơn | Dòng hàng có doanh thu lớn nhất của đơn: gán 1 người bán / 1 danh mục cho đơn (1,3% đơn có nhiều người bán) |
| `olap.mv_sales_cube` | tháng × danh mục × vùng/bang khách × bang người bán × trạng thái | Doanh thu, phí vận chuyển, số sản phẩm, số dòng hàng |
| `olap.mv_delivery_cube` | tháng × bang người bán × bang/vùng khách × trạng thái | Số đơn, đơn đã giao, đơn trễ, tổng ngày giao / ngày hẹn, doanh thu |
| `olap.mv_seller_scorecard` | 1 người bán | Doanh thu, số đơn, tỷ lệ trễ, ngày giao TB, điểm review |

Quy ước:

- `is_valid_sale` = đơn không ở trạng thái `canceled` / `unavailable`. Mọi KPI doanh thu mặc định chỉ tính đơn hợp lệ.
- Số đo trong `mv_*` đều cộng dồn được (sum, count). Tỷ lệ như tỷ lệ trễ tính lúc truy vấn bằng `sum(tử) / sum(mẫu)` nên roll-up lên cấp cao hơn vẫn đúng. Số đơn không nằm trong `mv_sales_cube` vì một đơn có thể có nhiều danh mục.
- Phân tích theo khách và vùng dùng đúng phiên bản địa chỉ khách tại thời điểm đặt (`customer_key` trong fact đã trỏ tới phiên bản SCD2 tương ứng).
- `tests/test_olap.py` kiểm tra số dòng của view bằng số dòng của fact và tổng trong `mv_*` khớp với fact.

## 2. KPI

| KPI | Công thức | Nguồn |
|---|---|---|
| Doanh thu | `sum(order_revenue)` đơn hợp lệ | `mv_delivery_cube` / `v_sales` |
| Số đơn | `count(order_id)` đơn hợp lệ | `mv_delivery_cube` |
| Giá trị đơn trung bình (AOV) | doanh thu / số đơn | |
| Phí vận chuyển / doanh thu | `sum(order_freight) / sum(order_revenue)` | |
| Tỷ lệ giao trễ | đơn trễ / đơn đã giao (`is_late`, so theo ngày) | |
| Thời gian giao TB | `avg(delivery_days)` đơn đã giao | |
| Điểm review TB | `avg(review_score)` của đơn trong bộ lọc | `v_review` nối `v_fulfillment` |
| Tỷ lệ trễ theo tuyến / bang / người bán | như trên, theo chiều tương ứng | |

## 3. Thao tác OLAP và truy vấn (`src/olap/queries`)

| Thao tác | File | Nội dung |
|---|---|---|
| KPI tổng | `01_kpi.sql` | Doanh thu, số đơn, AOV, tỷ lệ trễ, review |
| **Roll-up** | `02_rollup.sql` | `ROLLUP (năm, quý, tháng)` kèm `grouping()` nhận biết dòng tổng |
| **Cube** | `03_cube.sql` | `CUBE (vùng, năm)` và `GROUPING SETS` |
| **Drill-down** | `04_drilldown.sql` | Vùng → Bang → Thành phố (3 câu, mỗi câu thêm 1 cấp) |
| **Slice / Dice** | `05_slice_dice.sql` | Slice: cố định năm 2017. Dice: năm × vùng × danh mục, theo tháng |
| **Pivot** | `06_pivot.sql` | Danh mục × quý (FILTER); vùng × loại tuyến |
| Window | `07_window.sql` | Tăng trưởng theo tháng (MoM), doanh thu lũy kế, top-3 danh mục mỗi vùng |
| Logistics | `08_logistics.sql` | Tỷ lệ trễ theo tuyến, theo ngày thường / cuối tuần / lễ / Black Friday |
| Người bán, thanh toán, review | `09_sellers_payments_reviews.sql` | Scorecard, cơ cấu thanh toán, review khi giao trễ (drill-across qua `order_id`) |

Mỗi file chạy được bằng `psql -f` hoặc trong tab Truy vấn SQL của dashboard. `tests/test_olap.py` chạy thử tất cả.

## 4. Dashboard (`src/app`, chạy `streamlit run src/app/app.py`)

| Trang | Nội dung | Dữ liệu |
|---|---|---|
| Tổng quan | 6 KPI, doanh thu / số đơn theo tháng, top danh mục, doanh thu theo bang, cơ cấu thanh toán | `mv_sales_cube`, `mv_delivery_cube` |
| Logistics | Tỷ lệ trễ và thời gian giao theo tháng, bang, tuyến (heatmap người bán × khách), thời gian từng chặng, review khi trễ | `mv_delivery_cube`, `v_fulfillment` |
| Người bán | Scorecard, top doanh thu, tỷ lệ trễ so với review, mức tập trung doanh thu | `mv_seller_scorecard` |
| OLAP explorer | Chọn số đo và phân cấp (roll-up, drill-down bằng cách đổi mức chi tiết), slice, dice bằng bộ lọc, pivot, ROLLUP, tải CSV, xem SQL sinh ra; tab SQL chỉ đọc | `mv_sales_cube` |
| Mô hình ML | Đọc số liệu `reports/metrics`, biểu đồ `reports/figures` do P3 ghi ra | file |
| DSS ngày hẹn giao | Gợi ý số ngày hẹn theo tuyến × danh mục, what-if, độ nhạy, tuyến cần xem lại | `v_fulfillment`, `v_review` |

Biểu đồ dùng Altair, màu và font cấu hình trong `.streamlit/config.toml`. Mỗi tab chỉ chạy truy vấn khi được mở, kết quả truy vấn được cache 10 phút (tối đa 256 mục). Kiểm thử giao diện: `tests/test_app_pages.py`, `tests/test_charts.py`.

Bộ lọc chung ở thanh bên gồm khoảng tháng, vùng, bang, danh mục và chỉ đơn hợp lệ. Giá trị lọc đi qua tham số ràng buộc, tên cột lấy từ danh sách cố định. Tab SQL chỉ nhận một câu `SELECT` hoặc `WITH`, chạy trong giao dịch `READ ONLY`, tối đa 5.000 dòng và 15 giây.

## 5. Trang DSS và liên kết với P3

Trang DSS hiện tính từ phân phối thời gian giao thực tế trong kho (`src/olap/dss_baseline.py`), chưa dùng ML:

- Quyết định: số ngày hẹn giao P cho một tuyến × danh mục.
- Tỷ lệ trễ(P) = tỷ lệ đơn đã giao có `delivery_days > P`. Gợi ý = P nhỏ nhất để tỷ lệ trễ ≤ mục tiêu do người dùng đặt.
- Điểm review kỳ vọng(P) = điểm TB đúng hạn × (1 − trễ) + điểm TB khi trễ × trễ.
- Độ nhạy: xem gợi ý thay đổi ra sao khi mục tiêu nằm trong khoảng 1% đến 20%.
- Hạn chế: giữ nguyên phân phối quá khứ; chưa mô hình hóa việc hẹn dài làm khách bỏ đơn; phân khúc < 30 đơn không gợi ý.

Khi P3 có mô hình, có thể dùng dự đoán theo từng đơn thay cho `delivery_days` trong `dss_baseline.py`, và ghi số liệu vào `reports/metrics`, `reports/figures` để trang Mô hình ML hiển thị.
