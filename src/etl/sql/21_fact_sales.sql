-- fact_sales: 1 dòng = 1 sản phẩm trong 1 đơn, kèm quantity.
-- Các dòng order_items cùng (đơn, sản phẩm) có giá, phí vận chuyển, người bán, hạn giao giống hệt nhau
-- -> gộp lại không mất thông tin. Đơn không có sản phẩm không xuất hiện ở đây (R19).

INSERT INTO dw.fact_sales (
    order_id, product_key, seller_key, customer_key, order_status_key, purchase_date_key,
    quantity, unit_price, item_revenue, freight_total, item_weight_g,
    shipping_limit_date, is_shipping_limit_anomaly
)
WITH items AS (
    -- Gộp theo cả 6 cột: nếu dữ liệu sau này có (đơn, sản phẩm) khác giá/người bán,
    -- sẽ ra 2 dòng trùng khóa chính và ETL báo lỗi, không gộp sai âm thầm
    SELECT
        order_id, product_id, seller_id, price, freight_value, shipping_limit_date,
        count(*) AS quantity
    FROM staging.order_items_typed
    WHERE price IS NOT NULL                     -- R37: thiếu giá (không ép được kiểu) -> không nạp
    GROUP BY order_id, product_id, seller_id, price, freight_value, shipping_limit_date
)
SELECT
    i.order_id,
    coalesce(p.product_key, -1),
    coalesce(s.seller_key, -1),
    k.customer_key,
    k.order_status_key,
    k.purchase_date_key,
    i.quantity,
    i.price,
    i.price * i.quantity,
    i.freight_value * i.quantity,                                     -- R33: 0 giữ nguyên
    p.weight_g * i.quantity,                                          -- null nếu không có khối lượng
    i.shipping_limit_date,
    coalesce(i.shipping_limit_date >= DATE '2019-01-01', FALSE)       -- R25
FROM items i
JOIN staging.order_keys k ON k.order_id = i.order_id                  -- R36: bỏ đơn thiếu ngày đặt
LEFT JOIN dw.dim_product p ON p.product_id = i.product_id
LEFT JOIN dw.dim_seller s ON s.seller_id = i.seller_id
ORDER BY i.order_id, i.product_id;