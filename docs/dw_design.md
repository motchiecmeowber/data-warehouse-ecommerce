# Thiết kế kho dữ liệu

Thiết kế theo quy trình 4 bước của Kimball: chọn quy trình nghiệp vụ → khai báo grain → xác định dimension → xác định measure.

## Mô hình: Star, riêng nhánh địa lý tách bảng (outrigger)

```
                dim_date      dim_product (gộp danh mục)
                    \             /
dim_payment_type -- [ các bảng fact ] -- dim_order_status
                    /             \
           dim_customer        dim_seller
                    \             /
                    dim_geography
```

- Các dimension để **phẳng** (star): `dim_date`, `dim_product`, `dim_payment_type`, `dim_order_status`.
- Riêng **địa lý** tách thành `dim_geography`, dùng chung cho `dim_customer` và `dim_seller`.

### Căn cứ (kiểm tra phụ thuộc trên dữ liệu thật)

| Phân cấp | Kết quả | Quyết định |
|---|---|---|
| Sản phẩm → danh mục | Chặt (32.951 sản phẩm / 73 danh mục), nhưng danh mục chỉ có 2 thuộc tính (tên gốc, tên tiếng Anh) | Gộp danh mục vào `dim_product`: tách chỉ thêm JOIN, không có lợi |
| Mã bưu điện → thành phố | Không chặt: 39 mã của khách, 34 mã của người bán ứng với nhiều thành phố | Thành phố là thuộc tính của mã bưu điện (R31), không tách cấp riêng |
| Thành phố → bang | Không chặt theo tên: 163 tên thành phố có ở nhiều bang | Không tách bảng thành phố |
| Mã bưu điện → bang | Chặt sau khi áp R32 | Bang là thuộc tính của `dim_geography` |
| Bang → vùng | Chặt (27 bang, 5 vùng) nhưng bảng quá nhỏ | Gộp vào `dim_geography` |
| Khách hàng, người bán → địa lý | 2.162 mã bưu điện dùng chung cho cả khách và người bán | **Tách `dim_geography`** dùng chung |

### Lý do tách riêng nhánh địa lý

1. Dùng chung cho khách và người bán → cả hai dùng cùng một bộ địa lý đã làm sạch (conformed).
2. Các quy tắc làm sạch địa lý (R15, R16, R29–R32) chỉ áp dụng ở một bảng.
3. Tọa độ, vùng không lặp lại trên ~96 nghìn khách.
4. Tuyến giao hàng (bang người bán → bang khách) cho DSS lấy từ cùng một nguồn.

### Đánh đổi

Truy vấn theo địa lý cần thêm một JOIN (fact → khách/người bán → địa lý). Khắc phục bằng các view phẳng trong schema `olap` cho phần OLAP và ML.

## Bước 1–2: Quy trình nghiệp vụ và grain

| Fact | Quy trình nghiệp vụ | Nguồn | Grain (1 dòng = …) | Loại fact |
|---|---|---|---|---|
| `fact_sales` | Bán hàng | order_items | 1 sản phẩm trong 1 đơn (`order_id`, `product_id`), kèm `quantity` | Transaction |
| `fact_order_fulfillment` | Hoàn tất đơn hàng (giao hàng) | orders | 1 đơn hàng (`order_id`) | Accumulating snapshot |
| `fact_payment` | Thanh toán | order_payments | 1 lần thanh toán (`order_id`, `payment_sequential`) | Transaction |
| `fact_review` | Đánh giá | order_reviews (sau R13) | 1 review của 1 đơn (`review_id`, `order_id`) | Transaction |

### Căn cứ

- **`fact_sales` gộp theo sản phẩm trong đơn:** 7.088 cặp (đơn, sản phẩm) có nhiều dòng trong order_items, nhưng giá, phí vận chuyển, người bán, hạn giao cho vận chuyển giống hệt nhau trong mọi cặp → gộp thành 1 dòng kèm `quantity` không mất thông tin (112.650 → 102.425 dòng).
- **`fact_order_fulfillment` không có khóa người bán:** 1.278 đơn (1,3%) có nhiều người bán. Phân tích theo người bán / tuyến giao hàng nối với `fact_sales` qua `order_id` (drill-across).
- **`fact_payment` tách riêng:** 2.246 đơn dùng nhiều loại thanh toán → không gộp được vào grain đơn hàng.
- **`fact_review` tách riêng:** đánh giá là quy trình riêng với mốc thời gian riêng (tạo, trả lời review); nối với các fact khác qua `order_id`.

## Bước 3: Dimension

Bus matrix: xem [bus_matrix.md](bus_matrix.md).

| Dimension | Grain | Ghi chú |
|---|---|---|
| `dim_date` | 1 ngày | Role-playing: 5 vai trong `fact_order_fulfillment`, 2 vai trong `fact_review` |
| `dim_customer` | 1 phiên bản địa chỉ của 1 khách (`customer_unique_id`) | SCD Type 2 (R12); nối tới `dim_geography` |
| `dim_seller` | 1 người bán | Nối tới `dim_geography` (R34, R35) |
| `dim_geography` | 1 mã bưu điện | Outrigger dùng chung cho khách và người bán |
| `dim_product` | 1 sản phẩm | Gộp danh mục (tên gốc, tên tiếng Anh) |
| `dim_order_status` | 1 trạng thái đơn | Dimension riêng |
| `dim_payment_type` | 1 loại thanh toán | Dimension riêng |

### Các quyết định khác

- **`dim_customer` có ở cả 4 fact** để mọi quy trình phân tích được theo khách và địa lý.
- **`dim_order_status` có ở `fact_sales`** để lọc doanh thu của đơn bị hủy / không có hàng.
- **`shipping_limit_date` không nối với `dim_date`** (R25): giữ làm cột timestamp trong `fact_sales`.
- **Không tạo `dim_time`:** giữ timestamp đầy đủ (có giờ) trong `fact_order_fulfillment`; khi cần phân tích theo giờ thì lấy giờ từ timestamp.
- **`dim_order_status` và `dim_payment_type` để riêng, không gộp thành junk dimension:** hai thuộc tính nằm ở hai fact khác nhau, gộp không giảm được khóa nào.

## Bước 4: Measure

Đơn vị các khoảng thời gian: **ngày, có phần thập phân**. Khoảng thời gian để null khi thiếu mốc (R04) hoặc bị âm (R23).

### `fact_sales` (1 sản phẩm trong 1 đơn)

| Measure | Cách tính | Loại |
|---|---|---|
| `quantity` | Số dòng order_items gộp lại | Cộng dồn |
| `unit_price` | `price` | Không cộng |
| `item_revenue` | `unit_price × quantity` | Cộng dồn |
| `freight_total` | `freight_value × quantity` | Cộng dồn |
| `item_weight_g` | `product_weight_g × quantity` | Cộng dồn |
| `shipping_limit_date` | Giữ nguyên timestamp (không nối `dim_date`) | Thuộc tính |
| `is_shipping_limit_anomaly` | R25 | Cờ |

### `fact_order_fulfillment` (1 đơn)

| Measure | Cách tính | Loại |
|---|---|---|
| `item_count` | Tổng `quantity` của đơn | Cộng dồn |
| `seller_count` | Số người bán khác nhau trong đơn | Cộng dồn |
| `order_revenue` | Tổng `item_revenue` của đơn | Cộng dồn |
| `order_freight` | Tổng `freight_total` của đơn | Cộng dồn |
| `order_weight_g` | Tổng `item_weight_g` của đơn | Cộng dồn |
| `approval_days` | Ngày duyệt − ngày đặt | Không cộng |
| `handling_days` | Ngày giao vận chuyển − ngày duyệt | Không cộng |
| `transit_days` | Ngày khách nhận − ngày giao vận chuyển | Không cộng |
| `delivery_days` | Ngày khách nhận − ngày đặt | Không cộng |
| `promised_days` | Ngày hẹn giao − ngày đặt | Không cộng |
| `delay_days` | Ngày khách nhận − ngày hẹn giao (so theo ngày) | Không cộng |
| `is_delivered` | Có ngày khách nhận | Cờ |
| `is_late` | Ngày khách nhận > ngày hẹn giao (so theo ngày) | Cờ |
| `has_missing_milestone` | R03 | Cờ |
| `has_time_anomaly` | R22, R24 | Cờ |
| `order_purchase_timestamp` | Giữ timestamp đầy đủ (thay cho `dim_time`) | Thuộc tính |

### `fact_payment` (1 lần thanh toán)

| Measure | Cách tính | Loại |
|---|---|---|
| `payment_value` | Giữ nguyên (R28) | Cộng dồn |
| `payment_installments` | 0 → 1 (R26) | Không cộng |

### `fact_review` (1 review của 1 đơn)

| Measure | Cách tính | Loại |
|---|---|---|
| `review_score` | 1–5 | Không cộng |
| `has_comment` | R10 | Cờ |
| `response_days` | Ngày trả lời − ngày tạo review | Không cộng |

Không lưu nội dung bình luận (tiêu đề, nội dung) trong DW; bản gốc vẫn còn ở staging.

### Không đưa vào fact

- **Số đo tính được lúc truy vấn:** tỷ lệ phí vận chuyển / doanh thu, giá trị trung bình mỗi đơn, tỷ lệ trễ (= trung bình `is_late`).
- **Số đo phục vụ riêng một bài toán:** `distance_km` (khoảng cách người bán → khách) tính bằng view trong schema `olap` khi cần, từ tọa độ trong `dim_geography`.

Nguyên tắc: fact chỉ chứa số đo gốc; số đo cho từng bài toán cụ thể tính bằng view, để schema không phụ thuộc vào bài toán DSS.

## Quy ước khóa

| Quy ước | Quyết định | Lý do |
|---|---|---|
| Khóa của dimension | **Surrogate key** (số nguyên tự tăng, vd. `customer_key`); khóa gốc giữ làm cột thuộc tính để truy vết | Bắt buộc cho SCD2 (một khách nhiều phiên bản); JOIN bằng số nguyên nhanh và nhẹ hơn chuỗi 32 ký tự; không phụ thuộc khóa của hệ nguồn |
| Fact không tìm được dimension | Trỏ tới **dòng "Unknown"** (khóa = -1) trong mỗi dimension; khóa ngoại trong fact không bao giờ null | JOIN không làm mất dòng fact |
| Khóa của `dim_date` | Số nguyên `YYYYMMDD` (vd. `20171124`) | Dễ đọc, tính trực tiếp từ ngày |
| Thuộc tính `dim_date` | Ngày, tháng, quý, năm, thứ, cuối tuần, **ngày lễ Brazil**, **Black Friday** | Tỷ lệ trễ thay đổi mạnh theo thời điểm (11/2017: 12,4%) |

**Nếu dùng khóa gốc thay cho surrogate key:** với `dim_customer` (SCD2), mỗi `customer_unique_id` có nhiều dòng (một dòng mỗi phiên bản địa chỉ) → JOIN fact với dim theo khóa gốc sẽ nhân bản dòng fact, làm doanh thu, số đơn bị đếm trùng.
