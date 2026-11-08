# Bus matrix

Hàng: quy trình nghiệp vụ (bảng fact). Cột: dimension. ✓: fact có khóa nối tới dimension đó.

| Quy trình nghiệp vụ | dim_date | dim_customer | dim_product | dim_seller | dim_order_status | dim_payment_type |
|---|---|---|---|---|---|---|
| Bán hàng (`fact_sales`) | ✓ ngày đặt | ✓ | ✓ | ✓ | ✓ | |
| Hoàn tất đơn hàng (`fact_order_fulfillment`) | ✓ 5 vai: đặt, duyệt, giao vận chuyển, khách nhận, hẹn giao | ✓ | | | ✓ | |
| Thanh toán (`fact_payment`) | ✓ ngày đặt | ✓ | | | | ✓ |
| Đánh giá (`fact_review`) | ✓ 2 vai: tạo review, trả lời review | ✓ | | | | |

`dim_geography` không nối trực tiếp với fact: được dùng qua `dim_customer` và `dim_seller` (outrigger).
Mọi fact đều chứa `order_id` (degenerate dimension) để nối chéo giữa các quy trình.

## Dimension dùng chung (conformed)

- `dim_date`: cả 4 fact.
- `dim_customer` (kèm `dim_geography`): cả 4 fact.
- `dim_order_status`: `fact_sales`, `fact_order_fulfillment`.
