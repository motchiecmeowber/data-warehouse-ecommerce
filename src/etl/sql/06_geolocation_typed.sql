-- Bảng trung gian staging.geolocation_typed: geolocation đã bỏ dòng trùng (R15) và ép kiểu tọa độ (R37).

DROP TABLE IF EXISTS staging.geolocation_typed;

CREATE TABLE staging.geolocation_typed AS
SELECT
    zip_code_prefix,
    CASE WHEN pg_input_is_valid(lat, 'numeric') THEN lat::numeric END AS lat,
    CASE WHEN pg_input_is_valid(lng, 'numeric') THEN lng::numeric END AS lng,
    city,
    state
FROM (
    -- R15: bỏ dòng trùng hoàn toàn
    SELECT DISTINCT
        geolocation_zip_code_prefix AS zip_code_prefix,
        geolocation_lat             AS lat,
        geolocation_lng             AS lng,
        geolocation_city            AS city,
        geolocation_state           AS state
    FROM staging.geolocation
) AS d;

INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, 'R37', 'geolocation', g.geolocation_zip_code_prefix,
       v.column_name, v.raw_value, 'Không ép được sang numeric, để null'
FROM staging.geolocation g
CROSS JOIN LATERAL (VALUES
    ('geolocation_lat', g.geolocation_lat),
    ('geolocation_lng', g.geolocation_lng)
) AS v(column_name, raw_value)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, 'numeric');
