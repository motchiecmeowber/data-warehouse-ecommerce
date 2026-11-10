# Khảo sát dữ liệu nguồn

Dữ liệu: `data/raw` (bộ Olist đầy đủ). Script: `src/profiling/`.

## Bước 1 – Cấu trúc

| Bảng | Số dòng | Số cột |
|---|---|---|
| orders | 99.441 | 8 |
| order_items | 112.650 | 7 |
| order_payments | 103.886 | 5 |
| order_reviews | 99.224 | 7 |
| customers | 99.441 | 5 |
| sellers | 3.095 | 4 |
| products | 32.951 | 9 |
| geolocation | 1.000.163 | 5 |
| product_category_name_translation | 71 | 2 |

## Bước 2 – Thiếu dữ liệu

| Bảng.cột | Số null | Tỷ lệ | Nhận định |
|---|---|---|---|
| order_reviews.review_comment_title | 87.656 | 88,34% | Bình thường: khách không bắt buộc viết tiêu đề |
| order_reviews.review_comment_message | 58.247 | 58,70% | Bình thường: khách không bắt buộc viết bình luận |
| orders.order_approved_at | 160 | 0,16% | Bình thường với đơn canceled (141) và created (5); **lỗi với 14 đơn delivered** |
| orders.order_delivered_carrier_date | 1.783 | 1,79% | Bình thường với đơn chưa giao cho vận chuyển; **lỗi với 2 đơn delivered** |
| orders.order_delivered_customer_date | 2.965 | 2,98% | Bình thường với đơn chưa giao; **lỗi với 8 đơn delivered** |
| products.product_category_name (và name_lenght, description_lenght, photos_qty) | 610 | 1,85% | Thiếu cả 4 cột cùng lúc trên 610 sản phẩm; 1.603 dòng order_items dùng các sản phẩm này |
| products.weight_g, length/height/width_cm | 2 | 0,01% | Thiếu cả 4 cột cùng lúc; ngoài ra 4 sản phẩm có weight_g = 0 |

## Bước 3 – Khóa và trùng lặp

| Bảng | Khóa | Kết quả | Nhận định |
|---|---|---|---|
| orders | order_id | Duy nhất | Khóa chính |
| customers | customer_id | Duy nhất | Khóa chính, nhưng là mã **theo từng đơn** |
| customers | customer_unique_id | 96.096 giá trị / 99.441 dòng | Bình thường: 1 khách mua nhiều đơn có nhiều customer_id. Đây là mã khách thật |
| sellers | seller_id | Duy nhất | Khóa chính |
| products | product_id | Duy nhất | Khóa chính |
| order_items | order_id + order_item_id | Duy nhất | Khóa chính ghép |
| order_payments | order_id + payment_sequential | Duy nhất | Khóa chính ghép |
| order_reviews | review_id | Trùng 814 dòng | Một review gắn với nhiều đơn |
| order_reviews | order_id | Trùng 551 dòng | Một đơn có nhiều review |
| order_reviews | review_id + order_id | Duy nhất | Khóa chính ghép |
| geolocation | zip_code_prefix | 19.015 giá trị / 1.000.163 dòng | Không phải khóa: mỗi mã có nhiều tọa độ |
| product_category_name_translation | product_category_name | Duy nhất | Khóa chính |

Dòng trùng hoàn toàn: chỉ có ở geolocation (261.831 dòng); các bảng khác 0.

## Bước 4 – Quan hệ giữa các bảng

Bản ghi con không tìm thấy bản ghi cha:

| Quan hệ | Mồ côi | Nhận định |
|---|---|---|
| orders → customers, order_items → orders / products / sellers, payments → orders, reviews → orders | 0 | Khóa ngoại khớp hoàn toàn |
| products.product_category_name → translation | 13 sản phẩm, 2 danh mục (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`) | Thiếu bản dịch |
| customers.zip_code_prefix → geolocation | 278 khách, 157 mã | Không có tọa độ |
| sellers.zip_code_prefix → geolocation | 7 người bán, 7 mã | Không có tọa độ |

Bản ghi cha không có bản ghi con:

| Trường hợp | Số đơn | Nhận định |
|---|---|---|
| Đơn không có order_items | 775 | Chủ yếu unavailable (603), canceled (164); còn created 5, invoiced 2, **shipped 1** |
| Đơn không có thanh toán | 1 | Đơn `bfbd0f9bdef84302105ad712db648a6c`, delivered, có 3 sản phẩm: **lỗi** |
| Đơn không có review | 768 | Bình thường: khách không bắt buộc đánh giá (646 đơn delivered) |

## Bước 5 – Giá trị hợp lệ và nhất quán

**Ngày giờ:** cả 8 cột ép được sang timestamp, không có giá trị sai định dạng.

| Cột | Min | Max |
|---|---|---|
| order_purchase_timestamp | 2016-09-04 | 2018-10-17 |
| order_estimated_delivery_date | 2016-09-30 | 2018-11-12 |
| shipping_limit_date | 2016-09-19 | **2020-04-09** (4 dòng sau 2018-12-31) |
| review_answer_timestamp | 2016-10-07 | 2018-10-29 |

**Thứ tự mốc thời gian của đơn:**

| Kiểm tra | Số đơn vi phạm |
|---|---|
| Giao vận chuyển trước khi đặt | 166 |
| Giao vận chuyển trước khi duyệt | 1.359 |
| Khách nhận trước khi giao vận chuyển | 23 |
| Trạng thái khác delivered nhưng có ngày khách nhận | 6 |
| Duyệt trước khi đặt; khách nhận trước khi đặt; hẹn giao trước khi đặt | 0 |

**Giá trị số:**

| Cột | Nhận định |
|---|---|
| price | 0,85 – 6.735; không có giá ≤ 0 |
| freight_value | 383 dòng = 0: có thể là miễn phí vận chuyển, hợp lệ |
| payment_value | 9 dòng = 0 |
| payment_installments | 2 dòng = 0 (tối thiểu hợp lệ là 1) |
| payment_type | 3 dòng `not_defined` |
| review_score | 1–5, hợp lệ |
| product_weight_g | 4 sản phẩm = 0 |

**Tọa độ:** 42 dòng geolocation nằm ngoài lãnh thổ Brazil.

**Chữ:**

| Cột | Vấn đề |
|---|---|
| geolocation.geolocation_city | 73.442 dòng có dấu (vd. `são paulo`), 1 dòng khoảng trắng thừa |
| sellers.seller_city | 3 dòng có dấu |
| customers.customer_city, các cột state, product_category_name | Sạch |

**Mã bang:** customers và geolocation có 27 giá trị (đủ 26 bang + DF), sellers có 23.

**Mã bưu điện:** 8 mã thuộc nhiều bang; 8.556 mã có nhiều cách viết tên thành phố.

## Bước 6 – Phân phối

**Trạng thái đơn:** delivered 96.478 (97,0%); shipped 1.107; canceled 625; unavailable 609; invoiced 314; processing 301; created 5; approved 2.

**Theo thời gian:**

- 2016 rất thưa (09/2016: 4 đơn, 10/2016: 324, **11/2016: không có đơn**, 12/2016: 1).
- 01/2017 – 08/2018: 800 – 7.544 đơn/tháng, đỉnh 11/2017 (Black Friday).
- 09–10/2018: chỉ 20 đơn, chưa có đơn nào được giao.
- → **Giai đoạn phân tích: 01/2017 – 08/2018 (20 tháng).**

**Giao trễ** (ngày khách nhận > ngày hẹn giao): **6,77%** trên 96.470 đơn đã giao.

| Đặc điểm | Giá trị |
|---|---|
| Tháng trễ cao | 11/2017: 12,4%; 02/2018: 14,1%; 03/2018: 19,0% |
| Tháng trễ thấp | 06/2018: 1,2% |
| Bang nhiều đơn nhất | SP: 40.494 đơn (42%), trễ 4,5% |
| Bang trễ cao | AL 21,4%; MA 17,4%; SE 15,2%; PI 13,9%; CE 13,8%; BA 12,2%; RJ 12,1% |

**Mua lặp lại:** 93.099 khách chỉ mua 1 đơn; **3,12%** khách mua từ 2 đơn trở lên (tối đa 17 đơn).

**Hệ quả cho thiết kế:**

- Lọc giai đoạn 01/2017 – 08/2018 khi phân tích và train mô hình; vẫn nạp toàn bộ vào DW.
- Tỷ lệ trễ thay đổi mạnh theo tháng và theo bang → cần `dim_date` (tháng, ngày lễ, Black Friday) và `dim_geography` (bang, vùng) cho phân tích giao hàng.
- Khách gần như không mua lặp → không phân khúc khách theo RFM.

## Tổng hợp vấn đề

| # | Bảng.cột | Vấn đề | Số lượng | Tiêu chí chất lượng | Cách xử lý dự kiến |
|---|---|---|---|---|---|
| 1 | Các cột ngày giờ (orders, order_items, order_reviews) | Đọc thành chuỗi | 8 cột | Hợp lệ (kiểu dữ liệu) | Ép sang timestamp |
| 2 | customers/sellers/geolocation.*_zip_code_prefix | Đọc thành số, mất số 0 ở đầu | 3 cột | Nhất quán | Đọc dạng chuỗi, bù 0 cho đủ 5 chữ số |
| 3 | orders (delivered) | Thiếu mốc thời gian | 14 / 2 / 8 đơn | Đầy đủ | Giữ đơn, gắn cờ bất thường, không tính vào chỉ số giao hàng |
| 4 | products.product_category_name | Thiếu danh mục | 610 sản phẩm | Đầy đủ | Gán `unknown` |
| 5 | products kích thước/khối lượng | Thiếu hoặc bằng 0 | 2 + 4 sản phẩm | Đầy đủ, hợp lệ | Để null, gắn cờ |
| 6 | order_reviews.review_comment_* | Thiếu | 87.656 / 58.247 | — | Không xử lý; tạo cột `has_comment` |
| 7 | customers.customer_unique_id | Không duy nhất (theo thiết kế nguồn) | 3.345 dòng | — | Dùng `customer_unique_id` làm khóa nghiệp vụ của dim_customer |
| 8 | order_reviews | Một đơn nhiều review; một review nhiều đơn | 551 / 814 dòng | Duy nhất | Mỗi đơn giữ review mới nhất |
| 9 | geolocation | Dòng trùng hoàn toàn; nhiều tọa độ cho một mã | 261.831 dòng; 19.015 mã | Duy nhất | Xóa trùng, gom 1 tọa độ cho mỗi mã |
| 10 | products.product_category_name | Danh mục chưa có bản dịch | 2 danh mục, 13 sản phẩm | Toàn vẹn tham chiếu | Bổ sung bản dịch thủ công |
| 11 | customers/sellers.zip_code_prefix | Không có trong geolocation | 157 + 7 mã | Toàn vẹn tham chiếu | Vẫn tạo dòng địa lý, tọa độ để null |
| 12 | orders | Đơn không có dòng sản phẩm | 775 đơn | Toàn vẹn tham chiếu | Không đưa vào fact_sales; ghi vào error_queue |
| 13 | orders | Đơn delivered không có thanh toán | 1 đơn | Toàn vẹn tham chiếu | Ghi vào error_queue, gắn cờ |
| 14 | orders | Mốc thời gian sai thứ tự | 166 / 1.359 / 23 đơn | Nhất quán | Giữ đơn, gắn cờ `has_time_anomaly` |
| 15 | orders | Trạng thái khác delivered nhưng có ngày khách nhận | 6 đơn | Nhất quán | Gắn cờ |
| 16 | order_items.shipping_limit_date | Ngày quá xa (năm 2020) | 4 dòng | Hợp lệ | Gắn cờ; không mở rộng dim_date theo giá trị này |
| 17 | order_payments | payment_value = 0; installments = 0; type `not_defined` | 9 / 2 / 3 dòng | Hợp lệ | installments 0 → 1; `not_defined` → `unknown`; giữ value = 0 |
| 18 | products.product_weight_g | Bằng 0 | 4 sản phẩm | Hợp lệ | Đổi thành null, gắn cờ |
| 19 | geolocation | Tọa độ ngoài Brazil | 42 dòng | Hợp lệ | Loại trước khi gom tọa độ |
| 20 | geolocation/sellers.*_city | Tên có dấu, khoảng trắng thừa, nhiều cách viết | 73.442 + 3 dòng; 8.556 mã | Nhất quán | Bỏ dấu, viết thường, cắt khoảng trắng; mỗi mã lấy tên xuất hiện nhiều nhất |
| 21 | geolocation | Một mã thuộc nhiều bang | 8 mã | Nhất quán | Lấy bang xuất hiện nhiều nhất |
| 22 | sellers.seller_city | Tên bẩn: kèm bang (`auriflama/sp`, `rio de janeiro / rio de janeiro`), toàn số (`04482255`) | 15+ người bán | Hợp lệ, nhất quán | Lấy thành phố từ `dim_geography` theo mã bưu điện |
| 23 | sellers.seller_state | Khác bang trong geolocation của cùng mã; 17 mã của người bán ứng với nhiều bang | 35 người bán | Nhất quán | Lấy bang từ `dim_geography` theo mã bưu điện |

## Quy tắc tiền xử lý

### Nguyên tắc chung

- **Staging giữ nguyên bản gốc:** mọi cột nạp vào staging ở dạng chuỗi (text), không ép kiểu, không sửa giá trị.
- **Mọi xử lý thực hiện ở bước chuyển staging → dw** (Transform).
- **Lỗi ở từng dòng không làm dừng ETL:** dòng lỗi được ghi vào `etl_log.error_queue` (kèm mã quy tắc), ETL chạy tiếp các dòng còn lại.

### Nhóm 1 – Kiểu dữ liệu và định dạng

| Mã | Vấn đề | Bảng.cột | Điều kiện | Hành động |
|---|---|---|---|---|
| R01 | 1 | orders.order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date; order_items.shipping_limit_date; order_reviews.review_creation_date, review_answer_timestamp | Mọi giá trị | Ép sang `TIMESTAMP`. Giá trị khác null nhưng không ép được → để null, ghi `error_queue` |
| R02 | 2 | customers.customer_zip_code_prefix, sellers.seller_zip_code_prefix, geolocation.geolocation_zip_code_prefix | Mọi giá trị | Lưu dạng chuỗi; bù số 0 ở đầu cho đủ 5 ký tự (`LPAD(zip, 5, '0')`) |

### Nhóm 2 – Thiếu dữ liệu

| Mã | Vấn đề | Bảng.cột | Điều kiện | Hành động |
|---|---|---|---|---|
| R03 | 3 | orders (đơn delivered) | `order_status = 'delivered'` và thiếu một trong các mốc `order_approved_at`, `order_delivered_carrier_date`, `order_delivered_customer_date` | Vẫn nạp đơn; gắn cờ `has_missing_milestone = true`; **không điền giá trị thay thế** (thay thế làm sai các chỉ số thời gian) |
| R04 | 3 | Chỉ số giao hàng của đơn | `order_delivered_customer_date` null | Không tính số ngày giao và trạng thái trễ (để null), không đưa vào chỉ tiêu giao hàng. Đơn chỉ thiếu ngày duyệt hoặc ngày giao cho vận chuyển vẫn tính bình thường |
| R05 | 4 | products.product_category_name | Null | Gán `unknown` |
| R06 | 4 | products.product_name_lenght, product_description_lenght, product_photos_qty | Null | Giữ null (không gán 0) |
| R07 | 5 | products.product_weight_g | `= 0` | Đổi thành null; không điền giá trị thay thế |
| R08 | 5 | products.product_weight_g, length/height/width_cm | Null | Giữ null; không điền giá trị thay thế |
| R09 | 6 | order_reviews.review_comment_title, review_comment_message | Null | Giữ null |
| R10 | 6 | order_reviews | Mọi dòng | Tạo cột `has_comment = true` khi tiêu đề hoặc bình luận khác null |

### Nhóm 3 – Trùng lặp và khóa

| Mã | Vấn đề | Bảng.cột | Điều kiện | Hành động |
|---|---|---|---|---|
| R11 | 7 | customers.customer_unique_id | Mọi dòng | Dùng `customer_unique_id` làm khóa nghiệp vụ của `dim_customer`; `customer_id` chỉ dùng để nối đơn với khách |
| R12 | 7 | customers (khách có nhiều mã bưu điện) | Cùng `customer_unique_id` nhưng khác `customer_zip_code_prefix` giữa các đơn | SCD Type 2: mỗi địa chỉ là một phiên bản (`valid_from`, `valid_to`, `is_current`), mốc hiệu lực là ngày đặt đơn; fact trỏ tới phiên bản đúng tại thời điểm mua |
| R13 | 8 | order_reviews (một đơn nhiều review) | Cùng `order_id` có nhiều dòng | Giữ review có `review_answer_timestamp` mới nhất |
| R14 | 8 | order_reviews (một review nhiều đơn) | Cùng `review_id` gắn nhiều `order_id` | Giữ review cho mọi đơn |
| R15 | 9 | geolocation | Dòng trùng hoàn toàn | Xóa |
| R16 | 9 | geolocation (một mã nhiều tọa độ) | Cùng `geolocation_zip_code_prefix` | Gom 1 dòng mỗi mã: lat, lng lấy **trung vị** (tính sau khi loại tọa độ ngoài Brazil) |

### Nhóm 4 – Toàn vẹn tham chiếu

| Mã | Vấn đề | Bảng.cột | Điều kiện | Hành động |
|---|---|---|---|---|
| R17 | 10 | product_category_name_translation | Danh mục có trong products nhưng không có bản dịch | Tự bổ sung bản dịch: `pc_gamer` → `pc_gamer`; `portateis_cozinha_e_preparadores_de_alimentos` → `portable_kitchen_and_food_preparers` |
| R18 | 11 | customers/sellers.*_zip_code_prefix | Mã không có trong geolocation | Vẫn tạo dòng địa lý: thành phố, bang lấy từ customers/sellers; tọa độ null |
| R19 | 12 | orders (không có order_items) | Đơn không xuất hiện trong order_items | Không nạp vào `fact_sales`; vẫn nạp vào `fact_order_fulfillment` |
| R20 | 12 | orders (không có order_items, trạng thái bất thường) | Như R19 và `order_status` không phải `unavailable` hoặc `canceled` | Ghi `error_queue` |
| R21 | 13 | orders (delivered, không có thanh toán) | Đơn không xuất hiện trong order_payments | Vẫn nạp đơn; ghi `error_queue` |

### Nhóm 5 – Giá trị bất thường và nhất quán

| Mã | Vấn đề | Bảng.cột | Điều kiện | Hành động |
|---|---|---|---|---|
| R22 | 14 | orders | Mốc thời gian sai thứ tự: giao vận chuyển trước khi đặt hoặc trước khi duyệt; khách nhận trước khi giao vận chuyển | Giữ đơn và giữ nguyên các ngày; gắn cờ `has_time_anomaly = true` |
| R23 | 14 | Chỉ số giao hàng của đơn | Đơn có cờ `has_time_anomaly` | Vẫn tính vào chỉ số giao hàng (tổng thời gian từ lúc đặt đến lúc khách nhận); khoảng thời gian trung gian bị âm để null |
| R24 | 15 | orders | `order_status <> 'delivered'` nhưng có `order_delivered_customer_date` | Giữ nguyên trạng thái và ngày; gắn cờ `has_time_anomaly = true` |
| R25 | 16 | order_items.shipping_limit_date | Sau 2018-12-31 | Giữ giá trị; gắn cờ `is_shipping_limit_anomaly = true`; cột này không nối với `dim_date` |
| R26 | 17 | order_payments.payment_installments | `= 0` | Đổi thành 1 |
| R27 | 17 | order_payments.payment_type | `= 'not_defined'` | Đổi thành `unknown` |
| R28 | 17 | order_payments.payment_value | `= 0` | Giữ nguyên |
| R29 | 19 | geolocation | Tọa độ ngoài khung Brazil (lat < -33,8 hoặc > 5,3; lng < -74,0 hoặc > -34,7) | Loại trước khi gom tọa độ (R16) |
| R30 | 20 | customers.customer_city, sellers.seller_city, geolocation.geolocation_city | Mọi giá trị | Bỏ dấu, viết thường, cắt khoảng trắng |
| R31 | 20 | geolocation (một mã nhiều tên thành phố) | Cùng mã có nhiều tên sau khi chuẩn hóa (R30) | Lấy tên xuất hiện nhiều nhất |
| R32 | 21 | geolocation (một mã nhiều bang) | Cùng mã có nhiều `geolocation_state` | Lấy bang xuất hiện nhiều nhất |
| R33 | — | order_items.freight_value | `= 0` (383 dòng) | Giữ nguyên: miễn phí vận chuyển, hợp lệ |
| R34 | 22 | sellers.seller_city | Mọi dòng | Không dùng `seller_city`; thành phố lấy từ `dim_geography` theo mã bưu điện. Riêng người bán có mã không nằm trong geolocation (R18): cắt phần sau dấu `/` hoặc `\`, áp R30; giá trị toàn số → `unknown` |
| R35 | 23 | sellers.seller_state | Mọi dòng | Không dùng `seller_state`; bang lấy từ `dim_geography` theo mã bưu điện (R32). Riêng người bán có mã không nằm trong geolocation (R18): dùng `seller_state` |
| R36 | — | orders.order_purchase_timestamp | Null hoặc không ép được kiểu (R01); dữ liệu hiện tại: 0 dòng | Không nạp đơn vào các fact, ghi `error_queue`: đơn không có ngày đặt thì không có `purchase_date_key`, không tính được các khoảng thời gian |
