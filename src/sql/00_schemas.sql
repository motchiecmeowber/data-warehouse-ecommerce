-- Tạo các schema của kho dữ liệu
-- Phụ trách: A

CREATE SCHEMA IF NOT EXISTS staging;   -- dữ liệu thô từ CSV
CREATE SCHEMA IF NOT EXISTS dw;        -- star schema (dim + fact)
CREATE SCHEMA IF NOT EXISTS olap;      -- view / materialized view tổng hợp
CREATE SCHEMA IF NOT EXISTS ml;        -- feature, dự đoán, thông tin model
CREATE SCHEMA IF NOT EXISTS etl_log;   -- lịch sử chạy ETL, bảng lỗi
