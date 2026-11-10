-- Bảng trung gian staging.order_payments_typed: order_payments đã ép kiểu (R37).
-- R26, R27 áp ở đây để fact_payment và kiểm tra chất lượng dùng chung.

DROP TABLE IF EXISTS staging.order_payments_typed;

CREATE TABLE staging.order_payments_typed AS
SELECT
    order_id,
    CASE WHEN pg_input_is_valid(payment_sequential, 'smallint')
         THEN payment_sequential::smallint END          AS payment_sequential,
    CASE WHEN payment_type = 'not_defined' THEN 'unknown'                           -- R27
         ELSE payment_type END                          AS payment_type,
    CASE WHEN NOT pg_input_is_valid(payment_installments, 'integer') THEN NULL
         WHEN payment_installments::int = 0 THEN 1                                  -- R26: 0 -> 1
         ELSE payment_installments::int END             AS payment_installments,
    CASE WHEN pg_input_is_valid(payment_value, 'numeric')
         THEN payment_value::numeric END                AS payment_value          -- R28: 0 giữ nguyên
FROM staging.order_payments;

INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R37', 'order_payments', p.order_id || '-' || p.payment_sequential,
       v.column_name, v.raw_value, 'Không ép được sang ' || v.type_name || ', để null'
FROM staging.order_payments p
CROSS JOIN LATERAL (VALUES
    ('payment_sequential',   p.payment_sequential,   'smallint'),
    ('payment_installments', p.payment_installments, 'integer'),
    ('payment_value',        p.payment_value,        'numeric')
) AS v(column_name, raw_value, type_name)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, v.type_name);
