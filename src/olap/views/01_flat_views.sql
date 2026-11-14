-- View phẳng trong schema olap: nối sẵn fact với dimension và dim_geography.
-- is_valid_sale = đơn không bị hủy / không có hàng, dùng khi tính doanh thu.
-- Chạy: python -m src.olap.build

CREATE SCHEMA IF NOT EXISTS olap;

-- Bán hàng: 1 dòng = 1 sản phẩm trong 1 đơn (grain của fact_sales)
CREATE OR REPLACE VIEW olap.v_sales AS
SELECT
    f.order_id,
    d.full_date                                             AS purchase_date,
    d.year, d.quarter, d.month, d.month_name, d.year_month,
    d.day_name, d.is_weekend, d.is_holiday, d.is_black_friday,
    p.product_id,
    p.category_name_en                                      AS category,
    s.seller_id,
    gs.state_code                                           AS seller_state,
    gs.region                                               AS seller_region,
    gs.city                                                 AS seller_city,
    c.customer_unique_id,
    gc.state_code                                           AS customer_state,
    gc.region                                               AS customer_region,
    gc.city                                                 AS customer_city,
    os.order_status,
    (os.order_status NOT IN ('canceled', 'unavailable'))    AS is_valid_sale,
    f.quantity,
    f.unit_price,
    f.item_revenue,
    f.freight_total
FROM dw.fact_sales f
JOIN dw.dim_date         d  ON d.date_key         = f.purchase_date_key
JOIN dw.dim_product      p  ON p.product_key      = f.product_key
JOIN dw.dim_seller       s  ON s.seller_key       = f.seller_key
JOIN dw.dim_geography    gs ON gs.geography_key   = s.geography_key
JOIN dw.dim_customer     c  ON c.customer_key     = f.customer_key
JOIN dw.dim_geography    gc ON gc.geography_key   = c.geography_key
JOIN dw.dim_order_status os ON os.order_status_key = f.order_status_key;

-- Dòng hàng chính của đơn = dòng có doanh thu lớn nhất, dùng để gán cho mỗi đơn 1 người bán và 1 danh mục
-- (1,3% đơn có nhiều người bán).
CREATE OR REPLACE VIEW olap.v_order_main_item AS
SELECT DISTINCT ON (order_id) order_id, seller_key, product_key
FROM dw.fact_sales
ORDER BY order_id, item_revenue DESC, product_key;

-- Giao hàng: 1 dòng = 1 đơn (grain của fact_order_fulfillment), kèm tuyến và khoảng cách.
-- Đơn không có sản phẩm (R19) thì seller_*, category là NULL.
CREATE OR REPLACE VIEW olap.v_fulfillment AS
SELECT
    f.order_id,
    dp.full_date                                            AS purchase_date,
    dp.year, dp.quarter, dp.month, dp.year_month,
    dp.is_weekend, dp.is_holiday, dp.is_black_friday,
    f.order_purchase_timestamp,
    c.customer_unique_id,
    gc.state_code                                           AS customer_state,
    gc.region                                               AS customer_region,
    gc.city                                                 AS customer_city,
    p.category_name_en                                      AS category,
    s.seller_id,
    gs.state_code                                           AS seller_state,
    gs.region                                               AS seller_region,
    CASE WHEN gs.state_code IS NOT NULL
         THEN gs.state_code || ' → ' || gc.state_code END   AS route,
    CASE WHEN gs.state_code IS NOT NULL
         THEN CASE WHEN gs.state_code = gc.state_code THEN 'Cùng bang' ELSE 'Khác bang' END END
                                                            AS route_type,
    os.order_status,
    (os.order_status NOT IN ('canceled', 'unavailable'))    AS is_valid_sale,
    f.item_count, f.seller_count,
    f.order_revenue, f.order_freight, f.order_weight_g,
    f.approval_days, f.handling_days, f.transit_days,
    f.delivery_days, f.promised_days, f.delay_days,
    f.is_delivered, f.is_late, f.has_missing_milestone, f.has_time_anomaly,
    -- Khoảng cách đường chim bay (km, haversine); NULL nếu thiếu tọa độ
    CASE WHEN gs.has_coordinates AND gc.has_coordinates THEN round((
        2 * 6371 * asin(sqrt(
            power(sin(radians(gc.latitude - gs.latitude) / 2), 2)
          + cos(radians(gs.latitude)) * cos(radians(gc.latitude))
          * power(sin(radians(gc.longitude - gs.longitude) / 2), 2)
        )))::numeric, 1) END                                AS distance_km
FROM dw.fact_order_fulfillment f
JOIN dw.dim_date         dp ON dp.date_key = f.purchase_date_key
JOIN dw.dim_customer     c  ON c.customer_key = f.customer_key
JOIN dw.dim_geography    gc ON gc.geography_key = c.geography_key
JOIN dw.dim_order_status os ON os.order_status_key = f.order_status_key
LEFT JOIN olap.v_order_main_item mi ON mi.order_id = f.order_id
LEFT JOIN dw.dim_seller  s  ON s.seller_key = mi.seller_key
LEFT JOIN dw.dim_product p  ON p.product_key = mi.product_key
LEFT JOIN dw.dim_geography gs ON gs.geography_key = s.geography_key;

-- Thanh toán: 1 dòng = 1 lần thanh toán
CREATE OR REPLACE VIEW olap.v_payment AS
SELECT
    f.order_id, f.payment_sequential,
    d.full_date AS purchase_date, d.year, d.quarter, d.month, d.year_month,
    gc.state_code AS customer_state, gc.region AS customer_region,
    pt.payment_type,
    f.payment_installments, f.payment_value
FROM dw.fact_payment f
JOIN dw.dim_date         d  ON d.date_key = f.purchase_date_key
JOIN dw.dim_customer     c  ON c.customer_key = f.customer_key
JOIN dw.dim_geography    gc ON gc.geography_key = c.geography_key
JOIN dw.dim_payment_type pt ON pt.payment_type_key = f.payment_type_key;

-- Đánh giá: 1 dòng = 1 review của 1 đơn
CREATE OR REPLACE VIEW olap.v_review AS
SELECT
    f.review_id, f.order_id,
    d.full_date AS review_date, d.year, d.quarter, d.month, d.year_month,
    gc.state_code AS customer_state, gc.region AS customer_region,
    f.review_score, f.has_comment, f.response_days
FROM dw.fact_review f
JOIN dw.dim_date      d  ON d.date_key = f.review_creation_date_key
JOIN dw.dim_customer  c  ON c.customer_key = f.customer_key
JOIN dw.dim_geography gc ON gc.geography_key = c.geography_key;
