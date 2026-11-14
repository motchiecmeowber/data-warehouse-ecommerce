-- dim_customer: SCD Type 2 theo địa chỉ (R11, R12).
-- Mỗi khách (customer_unique_id) có 1 phiên bản mới mỗi khi mã bưu điện đổi so với đơn trước đó.
-- valid_from = ngày đặt đơn đầu tiên ở địa chỉ đó; valid_to = valid_from của phiên bản kế tiếp.

INSERT INTO dw.dim_customer (
    customer_unique_id, geography_key, valid_from, valid_to, is_current, "version"
)
WITH customer_orders AS (
    -- Mỗi customer_id ứng với đúng 1 đơn: lấy mã bưu điện và ngày đặt của đơn đó
    SELECT
        c.customer_unique_id,
        lpad(c.customer_zip_code_prefix, 5, '0') AS zip,
        o.order_purchase_timestamp              AS purchase_ts,
        o.order_id
    FROM staging.customers c
    JOIN staging.orders_typed o ON o.customer_id = c.customer_id
    WHERE o.order_purchase_timestamp IS NOT NULL                      -- R36
),
flagged AS (
    -- is_new = 1 khi mã bưu điện khác đơn liền trước của cùng khách (đơn đầu tiên luôn = 1)
    SELECT
        *,
        CASE WHEN zip IS DISTINCT FROM lag(zip) OVER w THEN 1 ELSE 0 END AS is_new
    FROM customer_orders
    WINDOW w AS (PARTITION BY customer_unique_id ORDER BY purchase_ts, order_id)
),
numbered AS (
    -- Cộng dồn is_new -> số thứ tự phiên bản
    SELECT
        *,
        sum(is_new) OVER (PARTITION BY customer_unique_id ORDER BY purchase_ts, order_id) AS version
    FROM flagged
),
versions AS (
    SELECT customer_unique_id, version, zip, min(purchase_ts) AS valid_from
    FROM numbered
    GROUP BY customer_unique_id, version, zip
)
SELECT
    v.customer_unique_id,
    coalesce(g.geography_key, -1),
    v.valid_from,
    coalesce(lead(v.valid_from) OVER w, TIMESTAMP '9999-12-31'),
    lead(v.valid_from) OVER w IS NULL,
    v.version
FROM versions v
LEFT JOIN dw.dim_geography g ON g.zip_code_prefix = v.zip
WINDOW w AS (PARTITION BY v.customer_unique_id ORDER BY v.version)
ORDER BY v.customer_unique_id, v.version;