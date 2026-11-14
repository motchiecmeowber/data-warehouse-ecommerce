-- dim_seller: 1 dòng mỗi người bán; thành phố, bang lấy qua dim_geography (R34, R35).

INSERT INTO dw.dim_seller (seller_id, geography_key)
SELECT
    s.seller_id,
    coalesce(g.geography_key, -1)
FROM staging.sellers s
LEFT JOIN dw.dim_geography g ON g.zip_code_prefix = lpad(s.seller_zip_code_prefix, 5, '0')
ORDER BY s.seller_id;