# DSS chọn đơn cần can thiệp

Quyết định được lập cho các đơn mua trong một ngày. Mỗi model cho một danh sách riêng. Thứ tự ưu tiên dựa trên lợi ích ròng kỳ vọng của việc can thiệp một lần vào đơn hàng.

    thiệt hại khi trễ = thiệt hại cơ sở × hệ số nhóm khách
    lợi ích ròng = P(trễ) × thiệt hại khi trễ × hiệu quả − chi phí

Hiệu quả là tỷ lệ đơn vốn sẽ trễ mà can thiệp có thể giúp giao đúng hạn. Chi phí và thiệt hại dùng cùng đơn vị tiền. Người vận hành chọn các giả định này. DSS chỉ chọn đơn có lợi ích dương và lấy tối đa số đơn đội vận hành xử lý được trong ngày. Khi hòa lợi ích, ưu tiên xác suất trễ cao hơn rồi mã đơn tăng dần.

## Chạy từ thư mục gốc repo

Cấu hình DATABASE_URL, chạy ETL và tạo model phiên bản 2. Pipeline dùng train/calibration/test theo thời gian trong ml.yaml; chỉ train được cân bằng. DSS dùng p_late đã hiệu chỉnh sigmoid trên calibration độc lập. Xem ml_design.md về cửa sổ thời gian, ngưỡng và metrics.

    python -m src.ml.late_risk --output-dir artifacts/models/late_risk/temporal_01
    python -m src.ml.kmean --start-year 2017 --end-year 2017 --as-of 2018-01-01

Snapshot chỉ nhận đơn đã giao trước cutoff, tham chiếu RFM tại cutoff. Giữ cả CSV và JSON metadata. DSS từ chối snapshot thiếu metadata hoặc từ tương lai, model cũ/chưa sẵn sàng tại ngày quyết định, và đơn trùng train/calibration. Không dùng snapshot khám phá của dashboard cho DSS.

Tạo factors.json ánh xạ tên nhóm trong customer_segments.csv sang hệ số thiệt hại. Ví dụ giả định:

    {"Khách mua lại": 1.5, "Khách chi tiêu cao nhất": 1.5, "Khách chi tiêu cao": 1.3, "Khách chi tiêu thấp": 1, "Khách lâu chưa mua": 1}

Khách thiếu trong snapshot nhận nhóm “Chưa phân nhóm” với hệ số 1. Ví dụ thử thiệt hại cơ sở 100 đơn vị tiền, chi phí 2 hoặc 5, hiệu quả 25% hoặc 50%, năng lực 10 đơn hoặc không giới hạn:

    python -m src.dss.whatif --day 2018-05-01 --model-dir artifacts/models/late_risk/temporal_01 --segments output/kmeans/customer_segments.csv --factors factors.json --loss 100 --cost 2 5 --efficacy 0.25 0.5 --capacity 10 all --output-dir output/dss/demo

CLI đọc các đơn đủ feature mua trong ngày từ DW, tạo seller history từ artifact và chỉ chấm điểm mỗi model một lần. Trong Python, gọi score_orders(model_dir, orders, segments, factors), sau đó run_whatif(scores, links, loss, costs, efficacies, capacities). Dùng None cho năng lực không giới hạn. Tham số đầu tiên trong mỗi danh sách xác định kịch bản gốc cho tornado.

## Đọc kết quả

- orders.csv gồm thiệt hại, lợi ích gộp/ròng nếu can thiệp, chi phí, thứ hạng và cờ selected cho từng đơn/model/kịch bản.
- summary.csv chỉ cộng chi phí và lợi ích của các đơn được chọn. Số đơn trễ kỳ vọng tránh được là tổng P(trễ) × hiệu quả trên các đơn đó.
- sellers.csv và routes.csv phân bổ số đơn và tổng xác suất trễ của toàn bộ ứng viên, cùng lợi ích thực hiện theo kịch bản. Mỗi đơn đóng góp đều cho các seller riêng biệt hoặc các tuyến riêng biệt nên số đơn phân bổ có thể là số thập phân. Tuyến là bang seller đến bang khách.
- sensitivity.csv và tornado.png thể hiện thay đổi tổng lợi ích khi thay riêng chi phí, thiệt hại cơ sở hoặc hiệu quả ±20%. Hiệu quả giới hạn ở [0, 1]. DSS chọn lại đơn ở mỗi đầu tham số, giữ nguyên năng lực.
- review_stats.csv mô tả lịch sử các đơn có review hợp lệ trong DW. Đơn có nhiều review được tính điểm sao và tỷ lệ review 1–2 sao trung bình trong đơn trước khi lấy trung bình theo trạng thái giao. Mỗi đơn có cùng trọng số. Các thống kê này dùng để đối chiếu giả định; giá trị tiền tệ và hiệu quả can thiệp do người dùng nhập.

Lợi ích và số đơn tránh trễ là kỳ vọng theo giả định. Đánh giá hiệu quả thực tế cần dữ liệu về các can thiệp đã thực hiện.

## Kiểm tra đóng góp phân khúc và tái lập báo cáo

segment_coverage.csv phân biệt khách khớp nhóm, chưa phân nhóm và hệ số khác 1.
segment_ablation.csv so cùng kịch bản với tất cả hệ số bằng 1: số đơn chọn, lợi ích,
số ID thay đổi và hai danh sách ID. So sánh lợi ích ở đây là theo hai giả định thiệt hại,
không chứng minh can thiệp hoặc K-Means tạo lợi ích thực tế.

Từ thư mục C:/DATAWARE-261, mặc định script dùng DW:

```bash
data-warehouse-ecommerce/.venv/Scripts/python.exe report_going_here/complete_todos.py --source dw --output-dir report_going_here/results/new_dw_run
```

Nếu chưa có DW, chỉ định --source local --raw-dir đường_dẫn_CSV. Pipeline fit/score
vẫn dùng chung, chuyển đổi dữ liệu đầu vào được tái tạo bằng pandas; provenance ghi
rõ không chạy PostgreSQL. Script ghi metrics, reliability, ngày demo, coverage toàn test,
hash dữ liệu/code và phiên bản thư viện. Dùng thư mục trống; không ghi đè run cũ.

Đối chiếu tổng p_late với số trễ quan sát chỉ là kiểm tra hồi cứu. Kỳ vọng không bắt buộc
bằng số quan sát trong một ngày. Theo dõi cả Brier/log loss và thay đổi tỷ lệ trễ;
calibration trên giai đoạn cũ vẫn có thể dự đoán dư cho giai đoạn mới.
