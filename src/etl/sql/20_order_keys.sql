-- Bảng trung gian staging.order_keys: tra sẵn các khóa dùng chung theo đơn cho cả 4 fact.
-- Không tìm được dimension -> -1.

DROP TABLE IF EXISTS staging.order_keys;

CREATE TABLE staging.order_keys AS
SELECT
    o.order_id,
    o.order_purchase_timestamp,
    coalesce(dc.customer_key, -1)       AS customer_key,
    coalesce(s.order_status_key, -1)    AS order_status_key,
    coalesce(d.date_key, -1)            AS purchase_date_key
FROM staging.orders_typed o
LEFT JOIN staging.customers c ON c.customer_id = o.customer_id
-- SCD2: chọn phiên bản khách đang hiệu lực tại thời điểm đặt đơn
LEFT JOIN dw.dim_customer dc
       ON dc.customer_unique_id = c.customer_unique_id
      AND o.order_purchase_timestamp >= dc.valid_from
      AND o.order_purchase_timestamp <  dc.valid_to
LEFT JOIN dw.dim_order_status s ON s.order_status = o.order_status
LEFT JOIN dw.dim_date d ON d.full_date = o.order_purchase_timestamp::date
WHERE o.order_purchase_timestamp IS NOT NULL;                         -- R36

CREATE UNIQUE INDEX ON staging.order_keys (order_id);