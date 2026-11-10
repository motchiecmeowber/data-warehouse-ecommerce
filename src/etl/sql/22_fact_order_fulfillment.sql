-- fact_order_fulfillment (accumulating snapshot): 1 dòng = 1 đơn, gồm cả đơn không có sản phẩm (R19).
-- Khoảng thời gian tính bằng ngày, có phần thập phân; null khi thiếu mốc (R04) hoặc bị âm (R23).

INSERT INTO dw.fact_order_fulfillment (
    order_id, customer_key, order_status_key,
    purchase_date_key, approved_date_key, carrier_date_key, delivered_date_key, estimated_date_key,
    order_purchase_timestamp, item_count, seller_count, order_revenue, order_freight, order_weight_g,
    approval_days, handling_days, transit_days, delivery_days, promised_days, delay_days,
    is_delivered, is_late, has_missing_milestone, has_time_anomaly
)
WITH order_items AS (
    -- Tổng hợp từ fact_sales (đã nạp ở bước trước)
    SELECT
        order_id,
        sum(quantity)                   AS item_count,
        count(DISTINCT seller_key)      AS seller_count,
        sum(item_revenue)               AS order_revenue,
        sum(freight_total)              AS order_freight,
        -- Chỉ tính tổng khối lượng khi mọi sản phẩm trong đơn đều có khối lượng
        CASE WHEN count(*) = count(item_weight_g) THEN sum(item_weight_g) END AS order_weight_g
    FROM dw.fact_sales
    GROUP BY order_id
),
o AS (
    SELECT
        t.order_id,
        t.order_status,
        t.order_purchase_timestamp      AS purchased,
        t.order_approved_at             AS approved,
        t.order_delivered_carrier_date  AS carrier,
        t.order_delivered_customer_date AS delivered,
        t.order_estimated_delivery_date AS estimated,
        k.customer_key,
        k.order_status_key,
        k.purchase_date_key
    FROM staging.orders_typed t
    JOIN staging.order_keys k ON k.order_id = t.order_id              -- R36
)
SELECT
    o.order_id,
    o.customer_key,
    o.order_status_key,
    o.purchase_date_key,
    coalesce(da.date_key, -1),
    coalesce(dc.date_key, -1),
    coalesce(dd.date_key, -1),
    coalesce(de.date_key, -1),
    o.purchased,
    coalesce(i.item_count, 0),
    coalesce(i.seller_count, 0),
    coalesce(i.order_revenue, 0),
    coalesce(i.order_freight, 0),
    i.order_weight_g,
    -- (mốc sau - mốc trước) đổi ra ngày; âm -> null (R23)
    CASE WHEN o.approved  >= o.purchased THEN round(extract(epoch FROM o.approved  - o.purchased) / 86400, 2) END,
    CASE WHEN o.carrier   >= o.approved  THEN round(extract(epoch FROM o.carrier   - o.approved)  / 86400, 2) END,
    CASE WHEN o.delivered >= o.carrier   THEN round(extract(epoch FROM o.delivered - o.carrier)   / 86400, 2) END,
    CASE WHEN o.delivered >= o.purchased THEN round(extract(epoch FROM o.delivered - o.purchased) / 86400, 2) END,
    CASE WHEN o.estimated >= o.purchased THEN round(extract(epoch FROM o.estimated - o.purchased) / 86400, 2) END,
    o.delivered::date - o.estimated::date,                            -- so theo ngày; âm = giao sớm
    o.delivered IS NOT NULL,
    o.delivered::date > o.estimated::date,                            -- null nếu chưa giao (R04)
    -- R03: đơn delivered thiếu một trong các mốc
    o.order_status = 'delivered'
        AND (o.approved IS NULL OR o.carrier IS NULL OR o.delivered IS NULL),
    -- R22: mốc sai thứ tự; R24: chưa delivered nhưng có ngày khách nhận
    coalesce(o.carrier < o.purchased, FALSE)
        OR coalesce(o.carrier < o.approved, FALSE)
        OR coalesce(o.delivered < o.carrier, FALSE)
        OR (o.order_status <> 'delivered' AND o.delivered IS NOT NULL)
FROM o
LEFT JOIN order_items i ON i.order_id = o.order_id
LEFT JOIN dw.dim_date da ON da.full_date = o.approved::date
LEFT JOIN dw.dim_date dc ON dc.full_date = o.carrier::date
LEFT JOIN dw.dim_date dd ON dd.full_date = o.delivered::date
LEFT JOIN dw.dim_date de ON de.full_date = o.estimated::date
ORDER BY o.order_id;

-- R20: đơn không có sản phẩm, trạng thái không phải unavailable/canceled -> ghi error_queue
INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R20', 'orders', o.order_id, 'order_status', o.order_status,
       'Đơn không có sản phẩm nhưng trạng thái không phải unavailable/canceled'
FROM staging.orders_typed o
WHERE o.order_status NOT IN ('unavailable', 'canceled')
  AND NOT EXISTS (SELECT 1 FROM staging.order_items_typed i WHERE i.order_id = o.order_id);

-- R21: đơn delivered không có thanh toán -> vẫn nạp, ghi error_queue
INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R21', 'orders', o.order_id, NULL, NULL,
       'Đơn delivered không có thanh toán'
FROM staging.orders_typed o
WHERE o.order_status = 'delivered'
  AND NOT EXISTS (SELECT 1 FROM staging.order_payments p WHERE p.order_id = o.order_id);