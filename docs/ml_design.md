# Thiết kế ML

Phạm vi ML gồm phân cụm khách hàng và dự đoán review tốt hoặc xấu.
Chạy notebook thực nghiệm trước, sau đó triển khai trong repo dựa trên kết quả đã chọn.

## Phân cụm khách hàng

Module: `src/ml/kmean.py`, hàm `run_kmeans(connection, output_path=...)`.
Chạy từ thư mục repo với `python -m src.ml.kmean` sau khi cấu hình `DATABASE_URL`.
Kết quả mặc định: `output/kmeans/customer_segments.csv`.

Dùng đơn đã giao trong DW, Frequency đếm đơn khác nhau và Monetary cộng tiền hàng,
không cộng phí vận chuyển. Recency lấy ngày mua cuối trong dữ liệu cộng một ngày.
Giới hạn Frequency/Monetary ở P99, log1p, đảo Recency rồi StandardScaler;
K-Means dùng K=5, random_state=42, n_init=10 như notebook `Olist_Customer_Clustering.ipynb`.

Đối chiếu trên dữ liệu Olist đã clean: 93.350 khách, khớp số khách và trung vị RFM
trong kết quả notebook đã lưu:

| Mã cụm trong lần thực nghiệm | Số khách | Recency trung vị (ngày) | Frequency trung vị | Monetary trung vị | Nhãn |
|---|---:|---:|---:|---:|---|
| 0 | 13.149 | 232 | 1 | 319,00 | Chi tiêu cao |
| 1 | 26.422 | 194 | 1 | 34,90 | Chi tiêu thấp |
| 2 | 2.801 | 200 | 2 | 182,10 | Khách mua lại |
| 3 | 16.523 | 471 | 1 | 79,90 | Lâu chưa mua |
| 4 | 34.455 | 156 | 1 | 109,00 | Mua gần hơn, chi tiêu tầm trung |

Nhãn được suy ra từ trung vị RFM của cụm, không gắn cứng với mã cụm.
Ban đầu là “Chi tiêu tầm trung”; các điều kiện sau ghi đè theo thứ tự:
Recency < P50 → mua gần hơn; Monetary < P25 → chi tiêu thấp;
Monetary > P75 → chi tiêu cao; Recency > P90 → lâu chưa mua;
Frequency > 1 → khách mua lại. Các phân vị tính trên toàn bộ khách của lần chạy.
Trong lần đối chiếu, P50/P90 Recency là 220/466 ngày và P25/P75 Monetary là
47,65/154,6975. Nhãn có thể thay đổi nếu dữ liệu DW khác dữ liệu thực nghiệm.

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
