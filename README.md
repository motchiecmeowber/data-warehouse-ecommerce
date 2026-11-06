# E-commerce Data Warehouse & DSS

Bài tập lớn môn **Kho dữ liệu và Hệ hỗ trợ quyết định (CO4031)** – HK261.

Xây dựng kho dữ liệu cho dữ liệu thương mại điện tử (Brazilian E-Commerce – Olist) và một hệ hỗ trợ quyết định dùng machine learning.

## Kiến trúc

```
CSV (data/raw) ──ETL──▶ PostgreSQL ──▶ OLAP views ──▶ Dashboard (Streamlit)
                         │  staging                      ▲
                         │  dw (star schema)             │
                         │  ml (feature, prediction) ◀── ML ──▶ DSS (what-if, gợi ý)
                         └  etl_log
```

| Thành phần | Công nghệ |
|---|---|
| Kho dữ liệu | PostgreSQL (Docker local) |
| ETL | Python (pandas, SQLAlchemy) |
| OLAP | SQL (ROLLUP, CUBE, materialized view) |
| ML | scikit-learn, LightGBM |
| Dashboard / DSS | Streamlit, Plotly |

## Cấu trúc thư mục

```
data-warehouse-ecommerce/
├── README.md
├── docker-compose.yml               # PostgreSQL local (cổng 5433)
├── .env.example                     # Mẫu cấu hình kết nối DB
├── requirements.txt
├── Makefile                         # Lệnh tắt: db, init, etl, train, score, app, test
│
├── configs/
│   ├── etl.yaml                     # Tên file nguồn, khung tọa độ Brazil, giai đoạn phân tích
│   └── ml.yaml                      # Mốc chia train/test theo thời gian, danh sách mô hình
│
├── data/
│   ├── README.md                    # Nguồn, cách tải, mô tả các file
│   ├── raw/                         # 9 file CSV gốc từ Kaggle (không commit)
│   └── sample/                      # Bộ mẫu ~1.500 đơn, giữ đúng quan hệ khóa (có commit)
│
├── src/
│   ├── common/                      # Dùng chung
│   │   ├── config.py                # Đọc .env và configs/*.yaml
│   │   └── db.py                    # Kết nối DB, chạy file SQL
│   │
│   ├── sql/                         # DDL – chạy bằng: python -m src.sql.init_db
│   │   ├── 00_schemas.sql           # staging, dw, olap, ml, etl_log
│   │   ├── 01_staging.sql
│   │   ├── 02_dimensions.sql
│   │   ├── 03_facts.sql
│   │   ├── 04_ml_tables.sql
│   │   ├── 05_etl_log.sql
│   │   └── init_db.py
│   │
│   ├── etl/                         # CSV → staging → dw
│   │   ├── extract.py
│   │   ├── transform/               # Làm sạch geolocation, tên thành phố, review, đơn hàng, danh mục
│   │   ├── load_dimensions.py
│   │   ├── load_facts.py
│   │   ├── quality_checks.py
│   │   ├── make_sample.py           # Tạo data/sample từ data/raw
│   │   └── run_etl.py
│   │
│   ├── olap/
│   │   ├── views/                   # Materialized view tổng hợp
│   │   └── queries/                 # ROLLUP, CUBE, drill-down, slice/dice
│   │
│   ├── ml/                          # Lớp dự đoán
│   │   ├── datasets.py              # Lấy dữ liệu từ dw, chia train/test theo thời gian
│   │   ├── features/                # Feature cấp đơn hàng và người bán (chống leakage)
│   │   ├── models/                  # Rủi ro giao trễ, thời gian giao, phân cụm tuyến
│   │   ├── train.py
│   │   ├── evaluate.py
│   │   └── predict.py
│   │
│   ├── dss/                         # Lớp ra quyết định
│   │   ├── decision_model.py
│   │   ├── whatif.py
│   │   ├── sensitivity.py
│   │   └── recommend.py
│   │
│   └── app/                         # Dashboard + giao diện DSS (Streamlit)
│       ├── app.py
│       ├── components/
│       └── pages/                   # Tổng quan, Logistics, Người bán, OLAP, Mô hình ML, DSS
│
├── artifacts/models/                # Model đã train (không commit)
├── notebooks/                       # EDA và thử nghiệm
├── tests/                           # Kiểm thử ETL và chống leakage
├── reports/
│   ├── figures/                     # Biểu đồ cho báo cáo
│   └── metrics/                     # Số liệu đánh giá mô hình
└── docs/
    ├── schema/                      # Sơ đồ star schema
    ├── bus_matrix.md
    ├── data_dictionary.md
    ├── etl_flow.md
    ├── olap_queries.md
    ├── ml_design.md
    └── dss_design.md
```

## Cài đặt và chạy

Yêu cầu: Python 3.10+, Docker Desktop.

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # rồi sửa DATABASE_URL nếu cần
```

### macOS

```bash
brew install libomp             # LightGBM cần thư viện OpenMP trên macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # rồi sửa DATABASE_URL nếu cần
```

Lưu ý trên macOS:

- Cần cài [Homebrew](https://brew.sh) trước để chạy `brew install libomp`.
- Dùng `python3` khi chưa kích hoạt venv. Sau khi chạy `source .venv/bin/activate` thì `python` sẽ trỏ vào Python của venv, nên các lệnh bên dưới dùng như nhau trên cả hai hệ điều hành.
- Docker Desktop có bản cho cả chip Apple Silicon (M1/M2/M3…) và Intel; image `postgres:16` chạy được trên cả hai.
- Có thể dùng `make db`, `make etl`, `make app`… (xem [Makefile](Makefile)) vì macOS có sẵn `make` sau khi cài Xcode Command Line Tools (`xcode-select --install`).

### Các bước chạy (chung cho Windows và macOS)

1. Tải dữ liệu theo hướng dẫn trong [data/README.md](data/README.md).
2. Khởi động database:
   ```bash
   docker compose up -d
   ```
3. Khởi tạo schema và bảng:
   ```bash
   python -m src.sql.init_db
   ```
4. Chạy ETL:
   ```bash
   python -m src.etl.run_etl
   ```
5. Train và chấm điểm mô hình:
   ```bash
   python -m src.ml.train
   python -m src.ml.predict
   ```
6. Mở dashboard:
   ```bash
   streamlit run src/app/app.py
   ```

## Phân công

| Nhiệm vụ | Thư mục chính |
|---|---|
| Tiền xử lý dữ liệu, thiết kế Star Schema và ETL | `src/sql`, `src/etl`, `docs/schema` |
| OLAP và Dashboard | `src/olap`, `src/app` |
| Phân tích nghiệp vụ, mô hình ML/DSS và đánh giá | `src/ml`, `src/dss` |

## Nguồn dữ liệu

Brazilian E-Commerce Public Dataset by Olist – https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
