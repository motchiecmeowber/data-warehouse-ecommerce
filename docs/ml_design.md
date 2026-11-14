# Thiết kế ML

Phạm vi ML gồm phân cụm khách hàng và dự đoán review tốt hoặc xấu.
Chạy notebook thực nghiệm trước, sau đó triển khai trong repo dựa trên kết quả đã chọn.

## Phân cụm khách hàng

Module: `src/ml/kmean.py`, hàm `run_kmeans(connection, start_year, end_year)`.
Trên dashboard, mở trang Mô hình ML, nhập năm bắt đầu/kết thúc rồi bấm phân cụm.
Ví dụ 2017–2018 lấy ngày mua từ 01/01/2017 đến hết 31/12/2018.
Đọc toàn bộ dữ liệu DW trong khoảng này, không lấy mẫu hoặc giới hạn số dòng.
Cần nạp bộ đầy đủ từ `data/raw/` vào DW trước khi chạy.

Chạy trực tiếp sau khi cấu hình `DATABASE_URL`:

```bash
python -m src.ml.kmean --start-year 2017 --end-year 2018
```

Kết quả: `output/kmeans/customer_segments.csv`, thay thế file kết quả cũ
chỉ sau khi train và ghi thành công.

Dùng đơn đã giao có tiền hàng lớn hơn 0. Đơn tiền hàng bằng 0 được loại;
tiền âm, không hữu hạn, thiếu khóa/ngày hoặc trùng đơn sẽ báo lỗi.
Frequency đếm đơn khác nhau; Monetary cộng tiền hàng, không gồm phí vận chuyển.
Recency lấy ngày mua cuối trong dữ liệu hợp lệ đã chọn cộng một ngày.
Giới hạn Frequency/Monetary ở P99, log1p, đảo Recency rồi StandardScaler.
K-Means dùng K=4, random_state=42, n_init=10. Cần ít nhất 4 hồ sơ RFM
khác nhau sau tiền xử lý.

Nhãn suy ra từ trung vị RFM của từng cụm, không gắn cứng với mã cụm:

1. Cụm có Frequency cao nhất: “Khách mua lại” nếu trung vị lớn hơn 1.
   Nếu không có cụm như vậy, chọn Monetary cao nhất: “Khách chi tiêu cao nhất”.
2. Trong các cụm còn lại, Recency cao nhất: “Khách lâu chưa mua”.
3. Hai cụm còn lại xếp theo Monetary: “Khách chi tiêu thấp”, “Khách chi tiêu cao”.

Đây là nhãn tương đối trong khoảng năm đã chọn. Khi bằng nhau, giữ thứ tự mã cụm.
Theo biểu đồ K=4 tham chiếu: cụm 0 chi tiêu thấp; cụm 1 lâu chưa mua;
cụm 2 mua lại; cụm 3 chi tiêu cao. Cần chạy lại trên DW để xác nhận kết quả.

CSV gồm customer_unique_id, recency_days, frequency, monetary,
avg_order_value, kmeans_cluster và kmeans_segment.

## Dự đoán review tốt/xấu

Chạy `python -m src.ml.review_quality` từ thư mục repo sau khi cấu hình `DATABASE_URL`.

Dùng Gradient Boosting với `max_depth=8` và `min_samples_split=5`, cùng Logistic
Regression và Random Forest để đối chiếu. Cả ba cân bằng trọng số theo tần suất lớp
trong tập train. Cách gán nhãn và tham số GBDT lấy từ [notebook của Sourav Barik](https://www.kaggle.com/code/souravbarik/customer-satisfaction-using-olist-dataset).

Mốc dự đoán là lúc giao xong. Mỗi đơn lấy review hợp lệ đầu tiên nếu review đó xuất
hiện sau lúc giao. Review 1–2 sao là nhãn `0` (xấu), 4–5 sao là nhãn `1` (tốt).
Đơn có review 3 sao bị loại khỏi dữ liệu train và test.

Tám feature gồm `estimated_workdays`, `actual_workdays`,
`delivery_workday_delta`, `is_late`, `average_product_value`, `total_order_value`,
`freight_ratio`, `purchase_weekday`. Ngày làm việc tính thứ Hai đến thứ Sáu,
chưa trừ ngày lễ Brazil. Giá trị hàng/cước và số sản phẩm lấy từ fact đơn hàng;
giá sản phẩm trung bình bằng `order_revenue / item_count`.

DW chỉ giữ khóa ngày giao và ngày trả lời review, nên ghép timestamp chính xác
từ `staging.orders` và `staging.order_reviews` để tránh thay đổi cách lọc/chia tập.
Cần nạp cả staging và DW trước khi chạy; các fact phải tổng hợp đủ dòng hàng sạch.
20% đơn giao mới nhất làm test, các đơn cùng timestamp ở cùng một tập.
Train chỉ dùng review đã biết trước mốc test. Mỗi tập phải có đủ hai lớp.
Đánh giá bằng accuracy, macro F1, ROC AUC và precision, recall, F1 của lớp xấu.
Baseline luôn đoán lớp phổ biến nhất trong tập train.

Mỗi lần chạy lưu vào thư mục riêng `artifacts/models/review_quality/<run_id>/`.

- `logistic_regression.joblib`: lưu cả StandardScaler, one-hot thứ trong tuần và model.
- `random_forest.joblib` và `gradient_boosting.joblib` lưu model riêng cho từng thuật toán.
- `metrics.csv`, `classification_report.csv`, `predictions.csv`, `run.json`.

Chỉ công bố thư mục kết quả sau khi ghi đủ cả ba model và các bảng đánh giá.

```python
import joblib
from src.ml.review_quality import predict_review

model = joblib.load("artifacts/models/review_quality/<run_id>/gradient_boosting.joblib")
predictions = predict_review(model, orders)  # order_id, prediction_at và tám feature ở trên
```
