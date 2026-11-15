# Thiết kế ML

Phạm vi ML gồm phân cụm khách hàng và dự đoán nguy cơ giao trễ.
Chạy notebook thực nghiệm trước, sau đó triển khai trong repo dựa trên kết quả đã chọn.

## Phân cụm khách hàng

Module: `src/ml/kmean.py`, hàm `run_kmeans(connection, start_year, end_year)`.
Trên dashboard, mở trang Phân cụm khách hàng, nhập năm bắt đầu/kết thúc ở thanh bên rồi bấm phân cụm.
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

## Dự đoán giao trễ tại thời điểm đặt hàng

Module `src/ml/late_risk.py`; chạy `python -m src.ml.late_risk --output-dir artifacts/models/late_risk/run_02`.
Cần DATABASE_URL, staging và DW đã ETL. `fit_models(data, links, output_dir)` là pipeline dùng chung với script báo cáo.

`configs/ml.yaml` quy định ba khoảng nửa mở: train [2017-01-01, 2018-02-01),
calibration [2018-02-01, 2018-05-01), test [2018-05-01, 2018-09-01).
Train/calibration chỉ nhận kết quả có max(ngày giao, ngày hẹn) nhỏ hơn mốc kết thúc của tập.
Test chỉ dùng đơn có nhãn và giữ tỷ lệ lớp tự nhiên. Không lấy mẫu test theo tỷ lệ 50:50.

Mười feature chỉ dùng thông tin có tại lúc mua: khoảng cách, cước, thời gian hẹn giao,
thứ/tháng mua, chỉ số kích thước/khối lượng, danh mục, ba thống kê lịch sử seller.
Seller history chỉ lấy từ tập train, với known_at nhỏ hơn thời điểm mua từng đơn;
nguồn lịch sử được đóng băng cho cả calibration/test, seller mới nhận 0.

Giữ ba model với tham số cố định của thực nghiệm cũ (LR C=0.001; RF 300 cây;
LightGBM 100 vòng). Chỉ train được cân bằng 10.000 đúng hạn + 10.000 trễ:
LR dùng SMOTE, RF/LightGBM dùng SMOTENC. Encoder/scaler chỉ fit train.
Sigmoid calibration dùng FrozenEstimator để không fit lại model; dữ liệu calibration
không resample. Ngưỡng nhãn tối đa F1 trên calibration, hòa lấy ngưỡng lớn hơn.
Không dùng test để chọn model, calibration hay ngưỡng.

`predict_late(bundle, orders)` trả order_id, risk_score (điểm thô), p_late (đã hiệu chỉnh),
threshold và predicted_label. Model cũ thiếu calibration bị từ chối, cần train lại.
Manifest phiên bản 2 lưu cấu hình, ID/count/tỷ lệ lớp từng tập, available_at=2018-05-01.
Model chỉ dùng cho ngày từ available_at; đây là thời điểm sẵn sàng trong mô phỏng lịch sử,
không phải ngày thực thi máy tính.

Mỗi run ghi ba bundle joblib, seller_history.joblib, manifest.json, metrics.csv,
predictions.csv và example_orders.csv vào thư mục mới. Metrics gồm ROC-AUC,
average precision và baseline tỷ lệ trễ, precision/recall/F1/confusion matrix,
Brier score và log loss trước/sau calibration. Script báo cáo thêm reliability diagram.
Calibration không bảo đảm hết sai lệch khi tỷ lệ trễ thay đổi theo thời gian.

## Snapshot K-Means cho DSS

Phân tích khám phá trên dashboard giữ cách gọi theo năm. Mô phỏng DSS phải dùng:

```bash
python -m src.ml.kmean --start-year 2017 --end-year 2017 --as-of 2018-01-01
```

Chỉ dùng đơn mua trong năm đã chọn, đã giao trước as_of; Recency tham chiếu as_of.
CSV có metadata JSON cùng tên, chứa cutoff và SHA256 để phát hiện CSV không khớp.
Dùng `load_snapshot(path)` khi truyền segments cho DSS. CSV khám phá không có metadata
không được dùng cho mô phỏng lịch sử.
