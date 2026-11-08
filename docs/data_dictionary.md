# Data dictionary

Mô tả các bảng trong schema `dw`. Thiết kế và căn cứ: xem [dw_design.md](dw_design.md). Quy tắc làm sạch (R01–R35): xem [data_profiling.md](data_profiling.md).

Quy ước chung:

- Khóa `*_key`: surrogate key (số nguyên). Mỗi dimension có dòng **Unknown** với khóa = `-1`.
- Khóa ngoại trong fact không bao giờ null: không tìm được dimension → `-1`.
- Mã gốc của hệ nguồn (chuỗi 32 ký tự) giữ làm cột thuộc tính để truy vết.
- Khoảng thời gian: đơn vị ngày, có phần thập phân.

## Dimension

### `dim_date`

Grain: 1 ngày. Phạm vi: 2016-09-01 → 2018-12-31.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `date_key` | INTEGER, PK | `YYYYMMDD`; `-1` = Unknown |
| `full_date` | DATE | Ngày |
| `day` | SMALLINT | Ngày trong tháng (1–31) |
| `month` | SMALLINT | Tháng (1–12) |
| `month_name` | TEXT | Tên tháng |
| `quarter` | SMALLINT | Quý (1–4) |
| `year` | SMALLINT | Năm |
| `year_month` | CHAR(7) | `YYYY-MM` |
| `day_of_week` | SMALLINT | 1 = thứ Hai … 7 = Chủ nhật |
| `day_name` | TEXT | Tên thứ |
| `is_weekend` | BOOLEAN | Thứ Bảy, Chủ nhật |
| `is_holiday` | BOOLEAN | Ngày lễ quốc gia Brazil |
| `holiday_name` | TEXT | Tên ngày lễ (null nếu không phải ngày lễ) |
| `is_black_friday` | BOOLEAN | Ngày Black Friday (thứ Sáu sau thứ Năm thứ tư của tháng 11) |

### `dim_geography`

Grain: 1 mã bưu điện (5 ký tự). Outrigger dùng chung cho `dim_customer` và `dim_seller`.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `geography_key` | INTEGER, PK | Surrogate key; `-1` = Unknown |
| `zip_code_prefix` | CHAR(5), UNIQUE | Mã bưu điện, bù 0 ở đầu (R02) |
| `city` | TEXT | Thành phố: bỏ dấu, viết thường (R30); tên xuất hiện nhiều nhất (R31) |
| `state_code` | CHAR(2) | Mã bang; bang xuất hiện nhiều nhất (R32) |
| `state_name` | TEXT | Tên bang |
| `region` | TEXT | Vùng: Norte, Nordeste, Centro-Oeste, Sudeste, Sul |
| `latitude` | NUMERIC(9,6) | Trung vị (R16), sau khi loại tọa độ ngoài Brazil (R29); null nếu không có (R18) |
| `longitude` | NUMERIC(9,6) | Như trên |
| `has_coordinates` | BOOLEAN | Có tọa độ hay không |

Nguồn: geolocation; mã có trong customers/sellers nhưng không có trong geolocation lấy thành phố, bang từ customers/sellers (R18, R34, R35). Tên bang và vùng: bảng tham chiếu 27 bang do nhóm bổ sung.

### `dim_customer` (SCD Type 2)

Grain: 1 phiên bản địa chỉ của 1 khách (R12).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `customer_key` | INTEGER, PK | Surrogate key; `-1` = Unknown |
| `customer_unique_id` | CHAR(32) | Mã khách thật (R11) |
| `geography_key` | INTEGER, FK → `dim_geography` | Địa chỉ của phiên bản |
| `valid_from` | TIMESTAMP | Ngày đặt đơn đầu tiên ở địa chỉ này |
| `valid_to` | TIMESTAMP | Ngày bắt đầu phiên bản kế tiếp; `9999-12-31` nếu là phiên bản hiện tại |
| `is_current` | BOOLEAN | Phiên bản hiện tại |
| `version` | SMALLINT | Số thứ tự phiên bản (1, 2, …) |

### `dim_seller`

Grain: 1 người bán.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `seller_key` | INTEGER, PK | Surrogate key; `-1` = Unknown |
| `seller_id` | CHAR(32), UNIQUE | Mã người bán gốc |
| `geography_key` | INTEGER, FK → `dim_geography` | Địa chỉ người bán (R34, R35) |

### `dim_product`

Grain: 1 sản phẩm. Danh mục gộp vào bảng (không tách `dim_category`).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `product_key` | INTEGER, PK | Surrogate key; `-1` = Unknown |
| `product_id` | CHAR(32), UNIQUE | Mã sản phẩm gốc |
| `category_name` | TEXT | Danh mục (tiếng Bồ Đào Nha); `unknown` nếu thiếu (R05) |
| `category_name_en` | TEXT | Danh mục tiếng Anh (R17) |
| `name_length` | INTEGER | Độ dài tên; null nếu thiếu (R06) |
| `description_length` | INTEGER | Độ dài mô tả; null nếu thiếu (R06) |
| `photos_qty` | INTEGER | Số ảnh; null nếu thiếu (R06) |
| `weight_g` | NUMERIC(10,2) | Khối lượng (g); 0 → null (R07, R08) |
| `length_cm` | NUMERIC(10,2) | Chiều dài (cm) |
| `height_cm` | NUMERIC(10,2) | Chiều cao (cm) |
| `width_cm` | NUMERIC(10,2) | Chiều rộng (cm) |

### `dim_order_status`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `order_status_key` | SMALLINT, PK | Surrogate key; `-1` = Unknown |
| `order_status` | TEXT, UNIQUE | delivered, shipped, canceled, unavailable, invoiced, processing, created, approved |

### `dim_payment_type`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `payment_type_key` | SMALLINT, PK | Surrogate key; `-1` = Unknown |
| `payment_type` | TEXT, UNIQUE | credit_card, boleto, voucher, debit_card, unknown (R27) |

## Fact

### `fact_sales`

Grain: 1 sản phẩm trong 1 đơn. PK: (`order_id`, `product_key`).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `order_id` | CHAR(32) | Mã đơn (degenerate dimension) |
| `product_key` | INTEGER, FK → `dim_product` | |
| `seller_key` | INTEGER, FK → `dim_seller` | |
| `customer_key` | INTEGER, FK → `dim_customer` | Phiên bản khách hiệu lực tại thời điểm đặt |
| `order_status_key` | SMALLINT, FK → `dim_order_status` | |
| `purchase_date_key` | INTEGER, FK → `dim_date` | Ngày đặt |
| `quantity` | INTEGER | Số đơn vị |
| `unit_price` | NUMERIC(10,2) | Đơn giá |
| `item_revenue` | NUMERIC(12,2) | `unit_price × quantity` |
| `freight_total` | NUMERIC(12,2) | `freight_value × quantity` (R33) |
| `item_weight_g` | NUMERIC(12,2) | `weight_g × quantity`; null nếu không có khối lượng |
| `shipping_limit_date` | TIMESTAMP | Hạn giao cho vận chuyển (không nối `dim_date`) |
| `is_shipping_limit_anomaly` | BOOLEAN | R25 |

### `fact_order_fulfillment` (accumulating snapshot)

Grain: 1 đơn. PK: `order_id`.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `order_id` | CHAR(32), PK | Mã đơn |
| `customer_key` | INTEGER, FK → `dim_customer` | |
| `order_status_key` | SMALLINT, FK → `dim_order_status` | |
| `purchase_date_key` | INTEGER, FK → `dim_date` | Ngày đặt |
| `approved_date_key` | INTEGER, FK → `dim_date` | Ngày duyệt |
| `carrier_date_key` | INTEGER, FK → `dim_date` | Ngày giao vận chuyển |
| `delivered_date_key` | INTEGER, FK → `dim_date` | Ngày khách nhận |
| `estimated_date_key` | INTEGER, FK → `dim_date` | Ngày hẹn giao |
| `order_purchase_timestamp` | TIMESTAMP | Thời điểm đặt (có giờ) |
| `item_count` | INTEGER | Tổng `quantity` của đơn; 0 nếu không có sản phẩm (R19) |
| `seller_count` | SMALLINT | Số người bán trong đơn |
| `order_revenue` | NUMERIC(12,2) | Tổng `item_revenue` |
| `order_freight` | NUMERIC(12,2) | Tổng `freight_total` |
| `order_weight_g` | NUMERIC(12,2) | Tổng `item_weight_g` |
| `approval_days` | NUMERIC(8,2) | Ngày duyệt − ngày đặt |
| `handling_days` | NUMERIC(8,2) | Ngày giao vận chuyển − ngày duyệt |
| `transit_days` | NUMERIC(8,2) | Ngày khách nhận − ngày giao vận chuyển |
| `delivery_days` | NUMERIC(8,2) | Ngày khách nhận − ngày đặt |
| `promised_days` | NUMERIC(8,2) | Ngày hẹn giao − ngày đặt |
| `delay_days` | NUMERIC(8,2) | Ngày khách nhận − ngày hẹn giao (so theo ngày) |
| `is_delivered` | BOOLEAN | Có ngày khách nhận |
| `is_late` | BOOLEAN | Ngày khách nhận > ngày hẹn giao (so theo ngày); null nếu chưa giao |
| `has_missing_milestone` | BOOLEAN | R03 |
| `has_time_anomaly` | BOOLEAN | R22, R24 |

Các khoảng thời gian null khi thiếu mốc (R04) hoặc bị âm (R23).

### `fact_payment`

Grain: 1 lần thanh toán. PK: (`order_id`, `payment_sequential`).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `order_id` | CHAR(32) | Mã đơn |
| `payment_sequential` | SMALLINT | Thứ tự lần thanh toán |
| `customer_key` | INTEGER, FK → `dim_customer` | |
| `purchase_date_key` | INTEGER, FK → `dim_date` | Ngày đặt |
| `payment_type_key` | SMALLINT, FK → `dim_payment_type` | |
| `payment_installments` | SMALLINT | Số kỳ trả góp; 0 → 1 (R26) |
| `payment_value` | NUMERIC(12,2) | Số tiền (R28) |

### `fact_review`

Grain: 1 review của 1 đơn (sau R13). PK: (`review_id`, `order_id`).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `review_id` | CHAR(32) | Mã review |
| `order_id` | CHAR(32) | Mã đơn |
| `customer_key` | INTEGER, FK → `dim_customer` | |
| `review_creation_date_key` | INTEGER, FK → `dim_date` | Ngày tạo review |
| `review_answer_date_key` | INTEGER, FK → `dim_date` | Ngày trả lời review |
| `review_score` | SMALLINT | 1–5 |
| `has_comment` | BOOLEAN | R10 |
| `response_days` | NUMERIC(8,2) | Ngày trả lời − ngày tạo review |
