# Luồng ETL

Đưa 9 file CSV Olist vào kho dữ liệu (schema `dw`), áp các quy tắc tiền xử lý R01–R37 ([data_profiling.md](data_profiling.md)), theo thiết kế trong [dw_design.md](dw_design.md) và [data_dictionary.md](data_dictionary.md).

Chạy toàn bộ bằng một lệnh (ở thư mục gốc repo):

```bash
python -m src.etl.run_etl                        # dữ liệu đầy đủ (data/raw)
python -m src.etl.run_etl --data-dir data/sample # bộ mẫu
```

Yêu cầu: database đã bật (`docker compose up -d`) và đã tạo bảng (`python -m src.sql.init_db`).

## Tổng quan

```
data/raw/*.csv ─┐
                ├─ 1. Extract ──▶ staging (TEXT, nguyên văn)             [giao dịch 1]
data/reference ─┘                    │
                                     ▼
                ┌─ 2. Ép kiểu (bảng trung gian *_typed) ──▶ error_queue (R01, R15, R36, R37)
                │                    │
                │                    ▼
                │  3. Nạp 7 dimension (R02, R05–R08, R11–R12, R16–R18, R27, R29–R35)
                │                    │                                          [giao dịch 2]
                │                    ▼
                │  4. Nạp 4 fact (R03–R04, R10, R13–R14, R19–R26, R28, R33) ──▶ error_queue (R20, R21)
                │                    │
                │                    ▼
                └─ 5. Kiểm tra chất lượng ──▶ etl_log.quality_check
                                     │
                                     ▼
                              etl_log.run_history (success / failed)
```

## Các quyết định

| Quyết định | Chọn | Lý do |
|---|---|---|
| Kiểu ETL | **ELT**: nạp thô vào staging, biến đổi bằng SQL trong PostgreSQL | Dữ liệu đã nằm trong database, SQL xử lý tập hợp nhanh; PostgreSQL có sẵn hàm cho các quy tắc: `unaccent` (R30), `mode()` (R31, R32), `percentile_cont` (R16), `pg_input_is_valid` (R01) |
| Vai trò của Python | Chỉ điều phối: đọc cấu hình, chạy file SQL theo thứ tự, ghi log | Logic biến đổi nằm hết trong SQL, đọc và kiểm tra trực tiếp được |
| Cách nạp | **Nạp lại toàn bộ** mỗi lần chạy: xóa sạch `dw`, nạp lại từ staging | Chạy lại luôn ra cùng kết quả. SCD2 vẫn đúng vì staging có đủ lịch sử đơn hàng |
| Lỗi từng dòng | Ghi `etl_log.error_queue`, ETL chạy tiếp | Theo nguyên tắc chung trong [data_profiling.md](data_profiling.md) |
| Lỗi hệ thống (SQL sai, mất kết nối, Ctrl+C) | Dừng, rollback, ghi `run_history.status = failed` kèm thông báo lỗi | Nạp **nguyên tử** (xem mục Giao dịch): kho không bao giờ ở trạng thái nạp dở |
| Kiểm tra chất lượng không đạt | Giữ dữ liệu, ghi `failed`, lệnh trả mã lỗi 1 | Không ai dùng số liệu sai mà không biết |
| Dữ liệu tham chiếu | File CSV trong `data/reference/`, nạp vào staging như dữ liệu nguồn | Dễ xem, dễ sửa, ghi được nguồn |

## Thành phần

| Thành phần | Vai trò |
|---|---|
| [configs/etl.yaml](../configs/etl.yaml) | Tên bảng staging → tên file CSV (nguồn và tham chiếu); khung tọa độ Brazil (R29) |
| [src/etl/run_etl.py](../src/etl/run_etl.py) | Điều phối 5 bước, mở / commit / rollback giao dịch, ghi `run_history`, in kết quả |
| [src/etl/extract.py](../src/etl/extract.py) | Bước 1 |
| [src/etl/load_dimensions.py](../src/etl/load_dimensions.py) | Xóa sạch `dw`, chạy SQL `0x` (bước 2) và `1x` (bước 3) |
| [src/etl/load_facts.py](../src/etl/load_facts.py) | Chạy SQL `2x` (bước 4) |
| [src/etl/quality_checks.py](../src/etl/quality_checks.py) | Chạy SQL `3x` (bước 5) |
| `src/etl/sql/*.sql` | Toàn bộ logic biến đổi, đánh số theo thứ tự chạy |
| [src/common/db.py](../src/common/db.py) | `execute_sql_file`: chạy 1 file SQL trên kết nối có sẵn (không commit), truyền biến cấu hình; `run_sql_file`: chạy 1 file trong giao dịch riêng (dùng cho `init_db`) |

## Giao dịch

| Giao dịch | Gồm | Lỗi giữa chừng thì |
|---|---|---|
| 1 | Bước 1: nạp cả 11 bảng staging | Staging giữ nguyên dữ liệu cũ |
| 2 | Bước 2–5: xóa sạch `dw`, nạp lại dimension, fact, ghi `error_queue`, `quality_check` | Rollback toàn bộ: `dw` giữ nguyên dữ liệu của lần chạy thành công trước; `error_queue` không ghi gì |

`run_history` ghi ngoài 2 giao dịch trên, nên lần chạy lỗi vẫn để lại dòng `failed` kèm thông báo.

Trong lúc giao dịch 2 chạy (khoảng 1 phút), `TRUNCATE` khóa các bảng `dw`: truy vấn của dashboard phải chờ tới khi nạp xong, không bao giờ thấy kho trống hoặc nạp dở.

Đã thử: giả lập lỗi sau khi nạp fact, và Ctrl+C giữa chừng → `dw` vẫn đủ 102.425 dòng `fact_sales` của lần trước, `run_history` ghi `failed`.

Python truyền giá trị vào SQL qua biến phiên của PostgreSQL (`set_config`), SQL đọc bằng `current_setting(...)`:

| Biến | Dùng ở |
|---|---|
| `etl.run_id` | Mọi lệnh ghi `error_queue`, `quality_check` |
| `etl.lat_min`, `etl.lat_max`, `etl.lng_min`, `etl.lng_max` | `12_dim_geography.sql` (R29), lấy từ `brazil_bbox` trong `etl.yaml` |

## Bước 1 – Extract

Nạp 9 file nguồn (`data/raw` hoặc thư mục `--data-dir`) và 2 file tham chiếu (`data/reference`) vào schema `staging`.

- Dùng lệnh `COPY ... FROM STDIN` của PostgreSQL: nhanh (1 triệu dòng geolocation trong vài giây) và giữ nguyên văn giá trị (mã bưu điện `01001` không bị đổi thành `1001` như khi dùng pandas).
- Mọi cột là `TEXT`; ô trống thành `NULL`.
- Mỗi bảng: `TRUNCATE` + `COPY`; cả 11 bảng chung 1 giao dịch.
- Tên cột lấy từ dòng header của file (bỏ ký tự BOM của file bảng dịch danh mục).

Dữ liệu tham chiếu nhóm bổ sung:

| File | Nội dung | Dùng cho |
|---|---|---|
| `brazil_states.csv` | 27 bang: mã, tên, vùng (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) | `dim_geography.state_name`, `region` |
| `brazil_holidays.csv` | Ngày lễ 2016–2018: 9 ngày lễ quốc gia và Carnaval, Corpus Christi (`ponto_facultativo`: nghỉ tùy chọn, nhưng ảnh hưởng mạnh tới mua sắm, giao hàng) | `dim_date.is_holiday`, `holiday_name` |

## Bước 2 – Ép kiểu (bảng trung gian)

Tạo lại mỗi lần chạy, nằm trong schema `staging`, dùng chung cho các bước sau.

| File | Bảng tạo ra | Quy tắc |
|---|---|---|
| `01_orders_typed.sql` | `staging.orders_typed` | R01: 5 cột ngày → `TIMESTAMP`; R36: ghi lỗi đơn thiếu ngày đặt |
| `02_order_items_typed.sql` | `staging.order_items_typed` | R01: `shipping_limit_date`; R37: `order_item_id`, giá, phí vận chuyển |
| `03_order_reviews_typed.sql` | `staging.order_reviews_typed` | R01: 2 cột ngày; R37: điểm |
| `04_order_payments_typed.sql` | `staging.order_payments_typed` | R37: 3 cột số; áp luôn R26, R27 để `dim_payment_type`, `fact_payment` và kiểm tra chất lượng dùng chung |
| `05_products_typed.sql` | `staging.products_typed` | R37: 7 cột số |
| `06_geolocation_typed.sql` | `staging.geolocation_typed` | R15: bỏ dòng trùng; R37: tọa độ |

Ép kiểu an toàn: `pg_input_is_valid(giá_trị, kiểu)` kiểm tra trước; giá trị không hợp lệ thành `NULL` và được ghi `error_queue`, thay vì làm lệnh báo lỗi và dừng cả ETL. Dòng thiếu cột bắt buộc bị loại khỏi fact (R37): order_items thiếu giá, order_payments thiếu `payment_sequential`.

Đã thử: chạy trên bản sao bộ mẫu có cài 5 giá trị sai (giá `abc`, tiền `1O.5`, thứ tự thanh toán `x`, độ dài tên `five`, vĩ độ `lat?`) → cả 5 được ghi `error_queue` với mã R37, ETL chạy hết, 19/19 kiểm tra đạt.

## Bước 3 – Nạp dimension

Trước khi nạp: `TRUNCATE` mọi bảng `dw` (`RESTART IDENTITY`: surrogate key đánh lại từ 1), rồi chạy lại `src/sql/02_dimensions.sql` để chèn lại các dòng Unknown (khóa `-1`).

| File | Dimension | Cách làm | Quy tắc |
|---|---|---|---|
| `11_dim_date.sql` | `dim_date` | Sinh mọi ngày 2016-09-01 → 2018-12-31 (`generate_series`), nối bảng ngày lễ. Black Friday: thứ Sáu từ ngày 23 đến 29 tháng 11 | — |
| `12_dim_geography.sql` | `dim_geography` | Geolocation (đã bỏ dòng trùng ở bước 2): chuẩn hóa tên thành phố, gom theo mã bưu điện (thành phố, bang: giá trị xuất hiện nhiều nhất; tọa độ: trung vị trên các điểm trong khung Brazil). Mã chỉ có ở customers/sellers: lấy thành phố, bang từ đó, tọa độ null. Nối bảng 27 bang để lấy tên bang, vùng | R02, R16, R18, R29–R32, R34, R35 |
| `13_dim_customer.sql` | `dim_customer` (SCD2) | Xếp đơn của mỗi khách theo ngày đặt; mã bưu điện đổi so với đơn trước → phiên bản mới. `valid_from` = ngày đặt đầu tiên ở địa chỉ đó; `valid_to` = `valid_from` của phiên bản kế tiếp, hoặc `9999-12-31` | R11, R12 |
| `14_dim_seller.sql` | `dim_seller` | Nối `dim_geography` theo mã bưu điện | R34, R35 |
| `15_dim_product.sql` | `dim_product` | Nối bảng dịch, cộng 2 bản dịch tự bổ sung | R05–R08, R17 |
| `16_dim_order_status.sql` | `dim_order_status` | Các trạng thái có trong dữ liệu | — |
| `17_dim_payment_type.sql` | `dim_payment_type` | Các loại thanh toán (đã đổi `not_defined` → `unknown` ở bước 2) | R27 |

Cách tạo phiên bản SCD2 (kỹ thuật "gaps and islands"):

1. Với mỗi đơn của khách, so mã bưu điện với đơn liền trước (`lag`): khác → đánh dấu `1`, giống → `0`.
2. Cộng dồn các dấu này theo thứ tự ngày đặt → số thứ tự phiên bản.
3. Gom theo (khách, phiên bản): ngày đặt nhỏ nhất là `valid_from`; `lead` lấy `valid_from` của phiên bản sau làm `valid_to`.

Ví dụ: khách đặt 4 đơn ở các mã A, B, C, A → 4 phiên bản (quay lại địa chỉ cũ vẫn là phiên bản mới, vì giữa hai lần đó khách ở nơi khác).

## Bước 4 – Nạp fact

| File | Nạp | Cách làm | Quy tắc |
|---|---|---|---|
| `20_order_keys.sql` | `staging.order_keys` (trung gian) | Tra 1 lần các khóa dùng chung theo đơn: `customer_key` (phiên bản SCD2 có `valid_from ≤ ngày đặt < valid_to`), `order_status_key`, `purchase_date_key`. Bỏ đơn thiếu ngày đặt | R36 |
| `21_fact_sales.sql` | `fact_sales` | Gộp order_items theo (đơn, sản phẩm, người bán, giá, phí, hạn giao) → `quantity`. Gộp theo cả 6 cột: nếu dữ liệu có cặp (đơn, sản phẩm) khác giá, sẽ ra 2 dòng trùng khóa chính và ETL báo lỗi thay vì gộp sai. Bỏ dòng thiếu giá | R19, R25, R33, R37 |
| `22_fact_order_fulfillment.sql` | `fact_order_fulfillment` | Tổng hợp số lượng, doanh thu, phí, khối lượng từ `fact_sales`; tính các khoảng thời gian (ngày, 2 chữ số thập phân), cờ trễ và cờ bất thường; ghi lỗi R20, R21 | R03, R04, R19–R24 |
| `23_fact_payment.sql` | `fact_payment` | 1 dòng mỗi lần thanh toán; bỏ dòng thiếu `payment_sequential` | R26–R28, R37 |
| `24_fact_review.sql` | `fact_review` | Mỗi đơn giữ review trả lời muộn nhất (`row_number`); review gắn nhiều đơn giữ cho mọi đơn | R09, R10, R13, R14 |

Khóa không tra được → `-1` (dòng Unknown). Riêng các ngày của `fact_order_fulfillment` và `fact_review`: không có mốc (vd. đơn chưa giao) → `-1`.

Hai cách hiểu quy tắc khi làm ETL:

- **R10:** bình luận chỉ gồm khoảng trắng coi như không có bình luận (9 review).
- **`order_weight_g`:** chỉ tính tổng khi mọi sản phẩm trong đơn đều có khối lượng; thiếu 1 sản phẩm → null, tránh tổng thấp hơn thực tế.

## Bước 5 – Kiểm tra chất lượng

`30_quality_checks.sql` chạy 19 phép kiểm tra, mỗi phép so giá trị mong đợi với giá trị thực tế; kết quả ghi `etl_log.quality_check` (cột `passed` do database tự tính).

| Nhóm | Số phép | Kiểm tra |
|---|---|---|
| `completeness` | 7 | Số dòng 4 fact khớp nguồn; đủ khách, sản phẩm, người bán. Giá trị mong đợi đã trừ các dòng bị loại có chủ đích (R36, R37), để kiểm tra không báo sai khi các quy tắc này xảy ra |
| `reconciliation` | 4 | Tổng doanh thu, phí vận chuyển, thanh toán khớp nguồn; doanh thu theo đơn = doanh thu theo sản phẩm |
| `referential` | 3 | Không fact nào trỏ Unknown cho khách, sản phẩm, người bán, ngày đặt |
| `scd2` | 2 | Mỗi khách đúng 1 phiên bản hiện tại; các phiên bản nối tiếp, không chồng lấn |
| `validity` | 3 | `is_late` chỉ null khi chưa giao; mọi mã bưu điện có tên bang; mọi sản phẩm có tên danh mục tiếng Anh |

Khóa chính, khóa ngoại, `CHECK` do database chặn ngay khi nạp, không kiểm tra lại.

## Nhật ký (`etl_log`)

| Bảng | Nội dung |
|---|---|
| `run_history` | 1 dòng mỗi lần chạy: thời điểm bắt đầu, kết thúc, nguồn dữ liệu, `running` / `success` / `failed`, thông báo lỗi |
| `error_queue` | 1 dòng mỗi dòng dữ liệu lỗi: mã quy tắc, bảng, khóa, cột, giá trị gốc, lý do |
| `quality_check` | 1 dòng mỗi phép kiểm tra mỗi lần chạy |

Xem lại lần chạy gần nhất:

```sql
SELECT * FROM etl_log.run_history ORDER BY run_id DESC LIMIT 1;
SELECT rule_code, count(*) FROM etl_log.error_queue WHERE run_id = <run_id> GROUP BY 1;
SELECT check_name, expected, actual, passed FROM etl_log.quality_check WHERE run_id = <run_id>;
```

## Kết quả trên dữ liệu đầy đủ

Thời gian chạy toàn bộ: khoảng 1–1,5 phút (Docker trên WSL).

| Bảng | Số dòng | Ghi chú |
|---|---|---|
| `dim_date` | 853 | 852 ngày + Unknown |
| `dim_geography` | 19.178 | 19.015 mã từ geolocation + 162 mã chỉ có ở khách/người bán (R18) + Unknown; 167 mã không có tọa độ |
| `dim_customer` | 96.353 | 96.096 khách, 250 khách có nhiều phiên bản địa chỉ |
| `dim_seller` | 3.096 | |
| `dim_product` | 32.952 | 610 sản phẩm danh mục `unknown` |
| `dim_order_status` | 9 | |
| `dim_payment_type` | 6 | |
| `fact_sales` | 102.425 | Gộp từ 112.650 dòng order_items |
| `fact_order_fulfillment` | 99.441 | Gồm 775 đơn không có sản phẩm; 23 đơn thiếu mốc (R03); 1.388 đơn bất thường thời gian (R22, R24) |
| `fact_payment` | 103.886 | |
| `fact_review` | 98.673 | |

| Đối chiếu | Nguồn | Kho |
|---|---|---|
| Doanh thu (`price`) | 13.591.643,70 | 13.591.643,70 |
| Phí vận chuyển | 2.251.909,54 | 2.251.909,54 |
| Thanh toán | 16.008.872,12 | 16.008.872,12 |
| Tỷ lệ giao trễ (đơn đã giao) | 6,77% (khảo sát) | 6,77% |

`error_queue`: R20 – 8 đơn (không có sản phẩm, trạng thái created/invoiced/shipped); R21 – 1 đơn delivered không có thanh toán. Không có lỗi ép kiểu (R01, R37) và đơn thiếu ngày đặt (R36).

## Lưu ý cho các phần dùng kho

- **Surrogate key đổi sau mỗi lần nạp lại** (`RESTART IDENTITY`). Với cùng dữ liệu nguồn thì khóa giữ nguyên (mọi lệnh nạp đều `ORDER BY`), nhưng dữ liệu thay đổi thì khóa có thể đổi. Bảng ngoài `dw` (vd. schema `ml`) nên lưu **khóa gốc** (`order_id`, `customer_unique_id`, `product_id`, `seller_id`), không lưu `*_key`.
- **Luôn ghi tên schema khi tạo bảng** (`olap.x`, `ml.x`): user database tên `dw` nên bảng tạo không ghi schema sẽ rơi vào schema `dw`.

Kiểm tra chất lượng: 19/19 đạt.
