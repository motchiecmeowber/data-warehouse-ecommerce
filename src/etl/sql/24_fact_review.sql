-- fact_review: 1 dòng = 1 review của 1 đơn.
-- R13: đơn có nhiều review -> giữ review trả lời muộn nhất. R14: review gắn nhiều đơn -> giữ cho mọi đơn.
-- Không lưu nội dung bình luận (R09: bản gốc vẫn ở staging).

INSERT INTO dw.fact_review (
    review_id, order_id, customer_key, review_creation_date_key, review_answer_date_key,
    review_score, has_comment, response_days
)
WITH latest AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY order_id
            ORDER BY review_answer_timestamp DESC NULLS LAST, review_creation_date DESC NULLS LAST, review_id
        ) AS rn
    FROM staging.order_reviews_typed
)
SELECT
    r.review_id,
    r.order_id,
    k.customer_key,
    coalesce(dc.date_key, -1),
    coalesce(da.date_key, -1),
    r.review_score,
    -- R10: có tiêu đề hoặc bình luận (chuỗi chỉ toàn khoảng trắng coi như không có)
    nullif(trim(r.review_comment_title), '') IS NOT NULL
        OR nullif(trim(r.review_comment_message), '') IS NOT NULL,
    CASE WHEN r.review_answer_timestamp >= r.review_creation_date
         THEN round(extract(epoch FROM r.review_answer_timestamp - r.review_creation_date) / 86400, 2) END
FROM latest r
JOIN staging.order_keys k ON k.order_id = r.order_id                  -- R36
LEFT JOIN dw.dim_date dc ON dc.full_date = r.review_creation_date::date
LEFT JOIN dw.dim_date da ON da.full_date = r.review_answer_timestamp::date
WHERE r.rn = 1
ORDER BY r.order_id;