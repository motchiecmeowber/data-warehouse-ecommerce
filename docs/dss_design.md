# DSS chọn đơn cần can thiệp

Quyết định được lập cho các đơn mua trong một ngày. Mỗi model cho một danh sách riêng. Thứ tự ưu tiên dựa trên lợi ích ròng kỳ vọng của việc can thiệp một lần vào đơn hàng.

    thiệt hại khi trễ = thiệt hại cơ sở × hệ số nhóm khách
    lợi ích ròng = P(trễ) × thiệt hại khi trễ × hiệu quả − chi phí

Hiệu quả là tỷ lệ đơn vốn sẽ trễ mà can thiệp có thể giúp giao đúng hạn. Chi phí và thiệt hại dùng cùng đơn vị tiền. Người vận hành chọn các giả định này. DSS chỉ chọn đơn có lợi ích dương và lấy tối đa số đơn đội vận hành xử lý được trong ngày. Khi hòa lợi ích, ưu tiên xác suất trễ cao hơn rồi mã đơn tăng dần.

## Chạy từ thư mục gốc repo

Cấu hình DATABASE_URL, chạy ETL và tạo bộ model mới. Fold 4 dùng cùng seed 42 và config đã chọn. Dùng toàn bộ outer train để xây dựng feature và lấy mẫu 10.000 On time + 10.000 Late. LR dùng SMOTE, RF/LightGBM dùng SMOTENC. Test là toàn bộ fold 4. DSS dùng trực tiếp predict_proba lớp Late cho p_late. Vì train cân bằng nên lợi ích tính từ điểm này là ước tính mô phỏng, có thể lệch so với thực tế.

    python -m src.ml.late_risk --output-dir artifacts/models/late_risk/full_fit

Chạy K-Means với lịch sử đã biết trước ngày quyết định. Ví dụ với đơn năm 2018, dùng snapshot từ năm 2017. Khi mô phỏng lịch sử, người chạy phải xác nhận các kết quả giao và dữ liệu dùng tạo phân nhóm đã có ở thời điểm đó.

    python -m src.ml.kmean --start-year 2017 --end-year 2017

Tạo factors.json ánh xạ tên nhóm trong customer_segments.csv sang hệ số thiệt hại. Ví dụ giả định:

    {"Khách mua lại": 1.5, "Khách chi tiêu cao nhất": 1.5, "Khách chi tiêu cao": 1.3, "Khách chi tiêu thấp": 1, "Khách lâu chưa mua": 1}

Khách thiếu trong snapshot nhận nhóm “Chưa phân nhóm” với hệ số 1. Ví dụ thử thiệt hại cơ sở 100 đơn vị tiền, chi phí 2 hoặc 5, hiệu quả 25% hoặc 50%, năng lực 10 đơn hoặc không giới hạn:

    python -m src.dss.whatif --day 2018-05-01 --model-dir artifacts/models/late_risk/full_fit --segments output/kmeans/customer_segments.csv --factors factors.json --loss 100 --cost 2 5 --efficacy 0.25 0.5 --capacity 10 all --output-dir output/dss/demo

CLI đọc các đơn đủ feature mua trong ngày từ DW, tạo seller history từ artifact và chỉ chấm điểm mỗi model một lần. Trong Python, gọi score_orders(model_dir, orders, segments, factors), sau đó run_whatif(scores, links, loss, costs, efficacies, capacities). Dùng None cho năng lực không giới hạn. Tham số đầu tiên trong mỗi danh sách xác định kịch bản gốc cho tornado.

## Đọc kết quả

- orders.csv gồm thiệt hại, lợi ích gộp/ròng nếu can thiệp, chi phí, thứ hạng và cờ selected cho từng đơn/model/kịch bản.
- summary.csv chỉ cộng chi phí và lợi ích của các đơn được chọn. Số đơn trễ kỳ vọng tránh được là tổng P(trễ) × hiệu quả trên các đơn đó.
- sellers.csv và routes.csv phân bổ số đơn và tổng xác suất trễ của toàn bộ ứng viên, cùng lợi ích thực hiện theo kịch bản. Mỗi đơn đóng góp đều cho các seller riêng biệt hoặc các tuyến riêng biệt nên số đơn phân bổ có thể là số thập phân. Tuyến là bang seller đến bang khách.
- sensitivity.csv và tornado.png thể hiện thay đổi tổng lợi ích khi thay riêng chi phí, thiệt hại cơ sở hoặc hiệu quả ±20%. Hiệu quả giới hạn ở [0, 1]. DSS chọn lại đơn ở mỗi đầu tham số, giữ nguyên năng lực.
- review_stats.csv mô tả lịch sử các đơn có review hợp lệ trong DW. Đơn có nhiều review được tính điểm sao và tỷ lệ review 1–2 sao trung bình trong đơn trước khi lấy trung bình theo trạng thái giao. Mỗi đơn có cùng trọng số. Các thống kê này dùng để đối chiếu giả định; giá trị tiền tệ và hiệu quả can thiệp do người dùng nhập.

Lợi ích và số đơn tránh trễ là kỳ vọng theo giả định. Đánh giá hiệu quả thực tế cần dữ liệu về các can thiệp đã thực hiện.
