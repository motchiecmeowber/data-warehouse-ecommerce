-- Bảng trung gian staging.order_reviews_typed: order_reviews đã ép kiểu.
-- R01: 2 cột ngày; R37: điểm review. Không ép được -> null, ghi error_queue.

DROP TABLE IF EXISTS staging.order_reviews_typed;

CREATE TABLE staging.order_reviews_typed AS
SELECT
    review_id,
    order_id,
    CASE WHEN pg_input_is_valid(review_score, 'smallint')
         THEN review_score::smallint END                AS review_score,
    review_comment_title,
    review_comment_message,
    CASE WHEN pg_input_is_valid(review_creation_date, 'timestamp')
         THEN review_creation_date::timestamp END        AS review_creation_date,
    CASE WHEN pg_input_is_valid(review_answer_timestamp, 'timestamp')
         THEN review_answer_timestamp::timestamp END     AS review_answer_timestamp
FROM staging.order_reviews;

INSERT INTO etl_log.error_queue (run_id, rule_code, source_table, record_key, column_name, raw_value, reason)
SELECT current_setting('etl.run_id')::int, v.rule_code, 'order_reviews', r.review_id || '-' || r.order_id,
       v.column_name, v.raw_value, 'Không ép được sang ' || v.type_name || ', để null'
FROM staging.order_reviews r
CROSS JOIN LATERAL (VALUES
    ('R01', 'review_creation_date',    r.review_creation_date,    'timestamp'),
    ('R01', 'review_answer_timestamp', r.review_answer_timestamp, 'timestamp'),
    ('R37', 'review_score',            r.review_score,            'smallint')
) AS v(rule_code, column_name, raw_value, type_name)
WHERE v.raw_value IS NOT NULL
  AND NOT pg_input_is_valid(v.raw_value, v.type_name);
