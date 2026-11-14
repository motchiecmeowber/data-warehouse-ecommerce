-- Bảng trung gian staging.orders_typed: orders đã ép kiểu ngày (R01), dùng chung cho dim_customer và các fact.
-- Biến etl.run_id do Python truyền vào (xem run_sql_file).

DROP TABLE IF EXISTS staging.orders_typed;

CREATE TABLE staging.orders_typed AS
SELECT
    order_id,
    customer_id,
    order_status,
    CASE WHEN pg_input_is_valid(order_purchase_timestamp, 'timestamp')
         THEN order_purchase_timestamp::timestamp END       AS order_purchase_timestamp,
    CASE WHEN pg_input_is_valid(order_approved_at, 'timestamp')
         THEN order_approved_at::timestamp END              AS order_approved_at,
    CASE WHEN pg_input_is_valid(order_delivered_carrier_date, 'timestamp')
         THEN order_delivered_carrier_date::timestamp END   AS order_delivered_carrier_date,
    CASE WHEN pg_input_is_valid(order_delivered_customer_date, 'timestamp')
         THEN order_delivered_customer_date::timestamp END  AS order_delivered_customer_date,
    CASE WHEN pg_input_is_valid(order_estimated_delivery_date, 'timestamp')
         THEN order_estimated_delivery_date::timestamp END  AS order_estimated_delivery_date
FROM staging.orders;

-- R01: giá trị khác null nhưng không ép được sang TIMESTAMP -> ghi error_queue
INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R01', 'orders', o.order_id, v.column_name, v.raw_value,
       'Không ép được sang TIMESTAMP, để null'
FROM staging.orders o
CROSS JOIN LATERAL (VALUES
    ('order_purchase_timestamp',      o.order_purchase_timestamp),
    ('order_approved_at',             o.order_approved_at),
    ('order_delivered_carrier_date',  o.order_delivered_carrier_date),
    ('order_delivered_customer_date', o.order_delivered_customer_date),
    ('order_estimated_delivery_date', o.order_estimated_delivery_date)
) AS v(column_name, raw_value)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, 'timestamp');

-- R36: thiếu ngày đặt -> không nạp vào fact, ghi error_queue
INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R36', 'orders', t.order_id, 'order_purchase_timestamp', o.order_purchase_timestamp,
       'Thiếu ngày đặt, không nạp vào fact'
FROM staging.orders_typed t
JOIN staging.orders o ON o.order_id = t.order_id
WHERE t.order_purchase_timestamp IS NULL;