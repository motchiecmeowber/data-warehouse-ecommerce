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
| `olap.mv_seller_scorecard` | 1 người bán | Doanh thu, số đơn, tỷ lệ trễ, ngày giao trung bình, điểm đánh giá |

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
| Thời gian giao trung bình | `avg(delivery_days)` đơn đã giao | |
| Điểm đánh giá trung bình | `avg(review_score)` của đơn trong bộ lọc | `v_review` nối `v_fulfillment` |
| Tỷ lệ trễ theo tuyến / bang / người bán | như trên, theo chiều tương ứng | |

## 3. Thao tác OLAP và truy vấn (`src/olap/queries`)

| Thao tác | File | Nội dung |
|---|---|---|
| KPI tổng | `01_kpi.sql` | Doanh thu, số đơn, AOV, tỷ lệ trễ, điểm đánh giá |
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
| Logistics | Tỷ lệ trễ và thời gian giao theo tháng, bang, tuyến (heatmap người bán × khách), thời gian từng chặng, điểm đánh giá khi giao trễ | `mv_delivery_cube`, `v_fulfillment` |
| Người bán | Scorecard, top doanh thu, tỷ lệ trễ so với điểm đánh giá, mức tập trung doanh thu | `mv_seller_scorecard` |
| OLAP explorer | Chọn số đo và phân cấp (roll-up, drill-down bằng cách đổi mức chi tiết), slice, dice bằng bộ lọc, pivot, ROLLUP, tải CSV, xem SQL sinh ra; tab SQL chỉ đọc | `mv_sales_cube` |
| Phân cụm khách hàng | Phân cụm khách hàng bằng K-Means theo RFM (P3) | `dw` |
| DSS ngày hẹn giao | Gợi ý số ngày hẹn theo tuyến × danh mục, what-if, độ nhạy, tuyến cần xem lại | `v_fulfillment`, `v_review` |
| DSS chọn đơn can thiệp (ML) | Chấm xác suất trễ các đơn mua trong một ngày bằng 3 mô hình của P3, chọn đơn có lợi ích ròng dương trong giới hạn năng lực, what-if theo chi phí × hiệu quả, độ nhạy ±20%, tuyến và người bán rủi ro, đối chiếu thực tế | `dw`, `artifacts/models/late_risk/<run>` |

Biểu đồ dùng Altair, màu và font cấu hình trong `.streamlit/config.toml`. Mỗi tab chỉ chạy truy vấn khi được mở, kết quả truy vấn được cache 10 phút (tối đa 256 mục). Kiểm thử giao diện: `tests/test_app_pages.py`, `tests/test_charts.py`.

Giao diện hiển thị nhãn tiếng Việt cho các giá trị mã (danh mục, trạng thái đơn, hình thức thanh toán, vùng) qua `src/app/components/labels.py`; truy vấn vẫn dùng mã gốc. Thẻ KPI dùng chung kiểu ở `src/app/components/kpi.py`, chỉ nhấn màu đỏ cho chỉ số giao trễ và xanh lá cho kết quả gợi ý.

Bộ lọc chung ở thanh bên gồm khoảng tháng, vùng, bang, danh mục và chỉ đơn hợp lệ. Giá trị lọc đi qua tham số ràng buộc, tên cột lấy từ danh sách cố định. Tab SQL chỉ nhận một câu `SELECT` hoặc `WITH`, chạy trong giao dịch `READ ONLY`, tối đa 5.000 dòng và 15 giây.

## 5. Trang DSS

### DSS ngày hẹn giao

Trang này tính từ phân phối thời gian giao thực tế trong kho (`src/olap/dss_baseline.py`), chưa dùng ML:

- Quyết định: số ngày hẹn giao P cho một tuyến × danh mục.
- Tỷ lệ trễ(P) = tỷ lệ đơn đã giao có `delivery_days > P`. Gợi ý = P nhỏ nhất để tỷ lệ trễ ≤ mục tiêu do người dùng đặt.
- Điểm đánh giá kỳ vọng(P) = điểm trung bình khi đúng hạn × (1 − tỷ lệ trễ) + điểm trung bình khi trễ × tỷ lệ trễ.
- Độ nhạy: xem gợi ý thay đổi ra sao khi mục tiêu nằm trong khoảng 1% đến 20%.
- Hạn chế: giữ nguyên phân phối quá khứ; chưa mô hình hóa việc hẹn dài làm khách bỏ đơn; nhóm đơn hàng dưới 30 đơn thì không gợi ý.

### DSS chọn đơn can thiệp (ML)

Trang này ra quyết định theo từng đơn, dùng mô hình rủi ro trễ và K-Means của P3 (cách tính: `docs/dss_design.md`). Trang chỉ gọi hàm của P3 và hiển thị:

- Đầu vào: lần huấn luyện (`artifacts/models/late_risk/<run>`, phiên bản 2, tạo bằng `python -m src.ml.late_risk --output-dir artifacts/models/late_risk/temporal_01`), ngày mua của các đơn cần xét (chỉ từ mốc `available_at` của mô hình, hiện là 01/05/2018), thiệt hại cơ sở, chi phí, hiệu quả và số đơn xử lý được trong ngày, hệ số thiệt hại theo nhóm khách.
- Dữ liệu: `load_orders(conn, decision_day=...)` đọc đơn trong ngày từ DW, `seller_history` thêm lịch sử người bán từ `seller_history.joblib`. Nhóm khách là snapshot `run_kmeans(..., as_of=ngày đầu tháng đang xét)`, đọc lại bằng `load_snapshot` (CSV + JSON metadata ở `artifacts/kmeans/`), chỉ dùng đơn đã giao trước mốc đó để không dùng dữ liệu tương lai.
- Tính toán: `score_orders` chấm xác suất trễ đã hiệu chỉnh một lần cho mỗi mô hình (từ chối mô hình cũ, snapshot từ tương lai hoặc đơn trùng train/calibration). `run_whatif` chạy kịch bản đang chọn cùng lưới chi phí (×0,5; ×1,5; ×2) × hiệu quả (10% đến 100%), kèm độ nhạy ±20%.
- Kết quả: KPI của kịch bản đang chọn, danh sách đơn nên can thiệp (tải CSV), bảng nhiệt what-if, biểu đồ độ nhạy, so sánh 3 mô hình, ảnh hưởng của hệ số nhóm khách (`segment_coverage`, `segment_ablation`), 10 tuyến và 10 người bán có nhiều đơn dự kiến trễ nhất.
- Đối chiếu: với các đơn thuộc tập kiểm tra của mô hình, so sánh tỷ lệ trễ thực tế giữa đơn được chọn và không được chọn, số trễ dự kiến với thực tế, và bảng chỉ số đánh giá P3 ghi trong `metrics.csv` (ROC-AUC, average precision, Brier, precision/recall/F1). Phần giả định có điểm đánh giá trung bình khi trễ và khi đúng hạn (`REVIEW_QUERY`) làm căn cứ cho thiệt hại.

Chưa có code hoặc model của P3 thì trang chỉ hiện hướng dẫn.
