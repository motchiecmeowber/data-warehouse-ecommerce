-- Bảng trung gian staging.order_items_typed: order_items đã ép kiểu.
-- R01: shipping_limit_date; R37: cột số. Không ép được -> null, ghi error_queue.

DROP TABLE IF EXISTS staging.order_items_typed;

CREATE TABLE staging.order_items_typed AS
SELECT
    order_id,
    CASE WHEN pg_input_is_valid(order_item_id, 'integer')
         THEN order_item_id::int END                    AS order_item_id,
    product_id,
    seller_id,
    CASE WHEN pg_input_is_valid(shipping_limit_date, 'timestamp')
         THEN shipping_limit_date::timestamp END        AS shipping_limit_date,
    CASE WHEN pg_input_is_valid(price, 'numeric')
         THEN price::numeric END                        AS price,
    CASE WHEN pg_input_is_valid(freight_value, 'numeric')
         THEN freight_value::numeric END                AS freight_value
FROM staging.order_items;

INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, v.rule_code, 'order_items', i.order_id || '-' || i.order_item_id,
       v.column_name, v.raw_value, 'Không ép được sang ' || v.type_name || ', để null'
FROM staging.order_items i
CROSS JOIN LATERAL (VALUES
    ('R01', 'shipping_limit_date', i.shipping_limit_date, 'timestamp'),
    ('R37', 'order_item_id',       i.order_item_id,       'integer'),
    ('R37', 'price',               i.price,               'numeric'),
    ('R37', 'freight_value',       i.freight_value,       'numeric')
) AS v(rule_code, column_name, raw_value, type_name)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, v.type_name);
