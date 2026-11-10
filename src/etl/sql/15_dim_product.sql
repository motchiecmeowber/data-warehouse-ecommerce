-- dim_product: 1 dòng mỗi sản phẩm, gộp danh mục (tên gốc, tên tiếng Anh).

INSERT INTO dw.dim_product (
    product_id, category_name, category_name_en, name_length, description_length, photos_qty,
    weight_g, length_cm, height_cm, width_cm
)
WITH translation AS (
    SELECT product_category_name, product_category_name_english
    FROM staging.product_category_name_translation
    UNION ALL
    -- R17: bổ sung bản dịch còn thiếu
    VALUES
        ('pc_gamer', 'pc_gamer'),
        ('portateis_cozinha_e_preparadores_de_alimentos', 'portable_kitchen_and_food_preparers')
)
SELECT
    p.product_id,
    coalesce(p.product_category_name, 'unknown'),                         -- R05
    CASE WHEN p.product_category_name IS NULL THEN 'unknown'
         ELSE t.product_category_name_english END,
    p.product_name_lenght::numeric::int,                                  -- R06: null giữ null
    p.product_description_lenght::numeric::int,
    p.product_photos_qty::numeric::int,
    nullif(p.product_weight_g::numeric, 0),                               -- R07: 0 -> null
    p.product_length_cm::numeric,                                         -- R08: null giữ null
    p.product_height_cm::numeric,
    p.product_width_cm::numeric
FROM staging.products p
LEFT JOIN translation t ON t.product_category_name = p.product_category_name
ORDER BY p.product_id;