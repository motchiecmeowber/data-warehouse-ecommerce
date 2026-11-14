-- dim_product: 1 dòng mỗi sản phẩm, gộp danh mục (tên gốc, tên tiếng Anh).

INSERT INTO dw.dim_product (
    product_id, category_name, category_name_en, name_length, description_length, photos_qty,
    weight_g, length_cm, height_cm, width_cm
)
WITH translation AS (
    SELECT product_category_name, product_category_name_english
    FROM staging.product_category_name_translation
    UNION ALL
    -- R17: bổ sung bản dịch còn thiếu (chỉ khi file dịch chưa có, tránh trùng)
    SELECT name, english
    FROM (VALUES
        ('pc_gamer', 'pc_gamer'),
        ('portateis_cozinha_e_preparadores_de_alimentos', 'portable_kitchen_and_food_preparers')
    ) AS extra(name, english)
    WHERE NOT EXISTS (
        SELECT 1 FROM staging.product_category_name_translation t WHERE t.product_category_name = extra.name
    )
)
SELECT
    p.product_id,
    coalesce(p.product_category_name, 'unknown'),                         -- R05
    CASE WHEN p.product_category_name IS NULL THEN 'unknown'
         ELSE t.product_category_name_english END,
    round(p.name_length)::int,                                            -- R06: null giữ null
    round(p.description_length)::int,
    round(p.photos_qty)::int,
    nullif(p.weight_g, 0),                                                -- R07: 0 -> null
    p.length_cm,                                                          -- R08: null giữ null
    p.height_cm,
    p.width_cm
FROM staging.products_typed p                                             -- đã ép kiểu (R37)
LEFT JOIN translation t ON t.product_category_name = p.product_category_name
ORDER BY p.product_id;