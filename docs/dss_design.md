# Late risk và mô phỏng ngày hẹn

`src/ml/late_risk.py` dùng ETL/features từ notebook độc lập. Chạy từ gốc repo:

```powershell
python -m src.ml.late_risk --data-dir data/raw --output-dir artifacts/models/late_risk/run_01
```

Thư mục raw cần bảy CSV Olist: orders, order_items, customers, sellers,
products, geolocation và product_category_name_translation. Dùng thư mục
output mới/rỗng để tránh trộn model giữa các lần chạy.

## Chọn model

So sánh SMOTE/SMOTENC trên năm outer fold (stratified, seed 42).
Mỗi outer train chia fit/validation 80/20; validation giữ toàn bộ Late và
lấy cùng số On time thật. Chỉ fit preprocessing và lịch sử seller trên fit.
SMOTE giữ cách encode của notebook; SMOTENC chuẩn hóa numeric và giữ category
khi tìm láng giềng, sau đó đổi numeric về đơn vị gốc để huấn luyện model.

Chọn ngưỡng có recall Late cao nhất với precision >= 60% trên validation;
hòa thì chọn F1, rồi ngưỡng cao hơn. Mỗi model chọn SMOTENC khi recall tốt hơn,
hoặc recall bằng nhưng precision cao hơn; bằng cả hai thì giữ SMOTE.
Chọn một fold chung theo recall trung bình ba model, rồi precision trung bình,
rồi fold nhỏ hơn. Nếu không có fold đủ điều kiện, dừng và báo lỗi.

Ba model cuối được refit trên outer train của fold đã chọn, mỗi model đúng
20.000 dòng (10.000 On time + 10.000 Late sau resampling). LR dùng C theo fold
đã tuning; RF/LightGBM giữ config notebook. Test là đơn thật 50:50, không dùng
chọn cấu hình. Báo cáo chỉ in ra console, không lưu metrics/biểu đồ vào artifact.

Output gồm ba bundle `.joblib` (model, encoder/scaler, ngưỡng, phương pháp,
fold/seed), `seller_history.joblib`, `manifest.json` chứa ID split và
`example_orders.csv`. Chỉ nạp joblib tin cậy do chính bạn tạo.

## What-if

Chức năng review cũ đã được thay bằng late risk; tham khảo cách so sánh
baseline/kịch bản của [World Model for Business](https://github.com/noorafaelhakimfaudka-droid/world-model-business).
Không dùng bảng kết quả tính sẵn hoặc hệ số ROI của repo tham khảo.

```powershell
python -m src.dss.whatif --model-dir artifacts/models/late_risk/run_01 --orders-file artifacts/models/late_risk/run_01/example_orders.csv --estimated-days 0 1 2 3
```

Hoặc gọi `run_whatif(model_dir, orders, estimated_days=3)` từ Python.
`--estimated-days` mặc định là 0, 1, 2, 3. Số âm cho phép hẹn sớm hơn,
nhưng ngày hẹn không được trước ngày mua. Không còn tham số `delivery_days`.

Đầu vào là một dòng mỗi đơn, không cần ngày giao thực tế hoặc nhãn:

- `order_id`, `order_purchase_timestamp`, `order_estimated_delivery_date`.
- `distance_km`, `freight_value`, `shipping_days_estimated` (làm tròn 2 chữ số).
- `order_weekday` (thứ Hai = 0), `order_purchase_month` (1..12).
- `item_physical_score`, `product_category_name`.
- `delayed_orders_by_seller`, `delay_rate_percent_by_seller` (0..100),
  `seller_avg_delay_days` (có thể âm).

Lịch sử seller phải được tính trước thời điểm mua, chỉ từ dữ liệu train.
Có thể dùng `seller_history(query, train, links)` và dữ liệu trong
`seller_history.joblib`; links phải bổ sung cặp order_id/seller_id của đơn mới.
Seller chưa có lịch sử nhận 0. Đơn nhiều seller dùng trung bình như notebook.
Module kiểm tra đầu vào và không tự loại đơn lỗi.

Mỗi đơn có hai dòng before/after cho mỗi model. Output gồm ngày hẹn,
`risk_score`, `threshold`, `predicted_label` (0 On time, 1 Late), `label`,
`risk_delta` (after trừ before), `baseline_label`. `summarize(results)` đếm
cảnh báo trước/sau và chuyển nhãn theo cả hai chiều.

Chỉ ngày hẹn và shipping_days_estimated thay đổi; lịch sử seller giữ nguyên.
Không ghi thay đổi vào DW hoặc train lại khi chạy what-if.

## Giới hạn

Precision >= 60% chỉ áp dụng validation 50:50; không bảo đảm ở test hoặc phân
bố thật. Điểm rủi ro chưa calibration. Chọn fold tốt nhất là thí nghiệm mang
tính khám phá: các outer fold chồng lấn dữ liệu phát triển, không thay thế một
tập holdout mới chưa từng dùng. Không coi đây là đánh giá độc lập triển khai.

Thay ngày hẹn có thể đổi nhãn trễ so với cam kết, không làm hàng giao nhanh
hơn và không chứng minh quan hệ nhân quả. Không ép điểm rủi ro phải giảm khi
cộng ngày: kết quả phản ánh model thực tế. Chưa thêm review, ROI hoặc UI.

Ngưỡng dự đoán cuối của cả ba model được đặt cố định 0,4 theo lựa chọn người dùng. Ngưỡng validation phía trên chỉ phục vụ chọn fold và phương pháp resampling.
