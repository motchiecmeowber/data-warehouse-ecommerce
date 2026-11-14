-- Bảng trung gian staging.products_typed: products đã ép kiểu (R37).

DROP TABLE IF EXISTS staging.products_typed;

CREATE TABLE staging.products_typed AS
SELECT
    product_id,
    product_category_name,
    CASE WHEN pg_input_is_valid(product_name_lenght, 'numeric')
         THEN product_name_lenght::numeric END          AS name_length,
    CASE WHEN pg_input_is_valid(product_description_lenght, 'numeric')
         THEN product_description_lenght::numeric END   AS description_length,
    CASE WHEN pg_input_is_valid(product_photos_qty, 'numeric')
         THEN product_photos_qty::numeric END           AS photos_qty,
    CASE WHEN pg_input_is_valid(product_weight_g, 'numeric')
         THEN product_weight_g::numeric END             AS weight_g,
    CASE WHEN pg_input_is_valid(product_length_cm, 'numeric')
         THEN product_length_cm::numeric END            AS length_cm,
    CASE WHEN pg_input_is_valid(product_height_cm, 'numeric')
         THEN product_height_cm::numeric END            AS height_cm,
    CASE WHEN pg_input_is_valid(product_width_cm, 'numeric')
         THEN product_width_cm::numeric END             AS width_cm
FROM staging.products;

INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R37', 'products', p.product_id,
       v.column_name, v.raw_value, 'Không ép được sang numeric, để null'
FROM staging.products p
CROSS JOIN LATERAL (VALUES
    ('product_name_lenght',        p.product_name_lenght),
    ('product_description_lenght', p.product_description_lenght),
    ('product_photos_qty',         p.product_photos_qty),
    ('product_weight_g',           p.product_weight_g),
    ('product_length_cm',          p.product_length_cm),
    ('product_height_cm',          p.product_height_cm),
    ('product_width_cm',           p.product_width_cm)
) AS v(column_name, raw_value)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, 'numeric');
