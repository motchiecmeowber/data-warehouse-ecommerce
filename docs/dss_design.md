# Thiết kế DSS

## What-if review tốt/xấu

`src/dss/whatif.py` nạp ba model review tốt/xấu từ cùng một lần huấn luyện,
dự đoán cho đơn gốc và đơn sau khi thay đổi ngày hẹn/ngày giao thực tế giả định.
Không huấn luyện lại model và không ghi thay đổi vào DW.

Đầu vào là DataFrame hoặc CSV gồm tám cột:

- `order_id`
- `order_purchase_timestamp`
- `order_approved_at`
- `order_delivered_customer_date`
- `order_estimated_delivery_date`
- `item_count`
- `order_revenue`: tổng tiền hàng, không gồm cước.
- `order_freight`: tổng cước.

`estimated_days` và `delivery_days` là số ngày lịch cộng vào ngày hẹn và ngày giao.
Số âm dịch ngày về trước. Ngày giao không được trước lúc duyệt đơn; ngày hẹn
không được trước ngày duyệt đơn. Đơn thiếu, trùng hoặc có tiền hàng/số lượng
không hợp lệ sẽ báo lỗi, không tự loại khỏi kết quả.

Các feature được tính lại bằng `clean_orders` và `build_features` của
`src/ml/review_quality.py`, bao gồm ngày làm việc, độ lệch và `is_late` theo ngày lịch.
Giá trị đơn, cước, số sản phẩm và ngày mua giữ nguyên.

```python
from src.dss.whatif import run_whatif

result = run_whatif(
    "artifacts/models/review_quality/<run_id>",
    orders,
    estimated_days=2,
    delivery_days=-1,
)
```

Hoặc chạy từ thư mục gốc repo:

```powershell
python -m src.dss.whatif --model-dir artifacts/models/review_quality/<run_id> --orders-file orders.csv --estimated-days 2 --delivery-days -1
```

Mỗi đơn có hai dòng `before` và `after` cho mỗi model Logistic Regression,
Random Forest và Gradient Boosting. Kết quả gồm `predicted_label` (0 là xấu, 1 là tốt),
`score_bad_review`, `score_good_review`, mốc giao (`prediction_at`) và ngày hẹn
(`estimated_delivery_date`).

Kết quả mô phỏng phản ánh quan hệ quan sát tại lúc giao hàng. Tác động thực tế của
việc đổi ngày hẹn cần được kiểm chứng riêng. Điểm xác suất từ model cân bằng trọng số
chưa được hiệu chỉnh theo phân bố review thực tế. Ngày làm việc chưa trừ lễ Brazil.

Trang Streamlit DSS hiện vẫn là khung TODO; module dùng được trực tiếp bằng Python hoặc CLI.
