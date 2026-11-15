-- Materialized view tổng hợp sẵn cho dashboard. Chỉ lưu số đo cộng dồn được (sum, count);
-- tỷ lệ tính lúc truy vấn bằng sum(tử) / sum(mẫu).
-- Làm mới sau mỗi lần ETL: python -m src.olap.build --refresh

-- Khối dữ liệu bán hàng: tháng x danh mục x bang khách x trạng thái
-- Không có số đơn vì một đơn có thể có nhiều danh mục; số đơn lấy từ mv_delivery_cube.
DROP MATERIALIZED VIEW IF EXISTS olap.mv_sales_cube CASCADE;
CREATE MATERIALIZED VIEW olap.mv_sales_cube AS
SELECT
    year, quarter, month, year_month,
    category, customer_region, customer_state, seller_state, order_status, is_valid_sale,
    sum(item_revenue)   AS revenue,
    sum(freight_total)  AS freight,
    sum(quantity)       AS units,
    count(*)            AS line_items
FROM olap.v_sales
GROUP BY year, quarter, month, year_month,
         category, customer_region, customer_state, seller_state, order_status, is_valid_sale;
CREATE INDEX ON olap.mv_sales_cube (year_month);
CREATE INDEX ON olap.mv_sales_cube (customer_state);

-- Khối dữ liệu giao hàng: tháng x tuyến x trạng thái (đơn đã giao)
DROP MATERIALIZED VIEW IF EXISTS olap.mv_delivery_cube CASCADE;
CREATE MATERIALIZED VIEW olap.mv_delivery_cube AS
SELECT
    year, quarter, month, year_month,
    seller_state, customer_state, customer_region, order_status, is_valid_sale,
    count(*)                                        AS orders,
    count(*) FILTER (WHERE is_delivered)            AS delivered_orders,
    count(*) FILTER (WHERE is_late)                 AS late_orders,
    sum(delivery_days)                              AS sum_delivery_days,
    count(delivery_days)                            AS n_delivery_days,
    sum(promised_days)                              AS sum_promised_days,
    count(promised_days)                            AS n_promised_days,
    sum(order_revenue)                              AS revenue,
    sum(order_freight)                              AS freight
FROM olap.v_fulfillment
GROUP BY year, quarter, month, year_month,
         seller_state, customer_state, customer_region, order_status, is_valid_sale;
CREATE INDEX ON olap.mv_delivery_cube (year_month);

-- Bảng điểm người bán (scorecard): 1 dòng = 1 người bán
DROP MATERIALIZED VIEW IF EXISTS olap.mv_seller_scorecard CASCADE;
CREATE MATERIALIZED VIEW olap.mv_seller_scorecard AS
WITH seller_orders AS (
    SELECT DISTINCT s.seller_key, f.order_id
    FROM dw.fact_sales f
    JOIN dw.dim_seller s ON s.seller_key = f.seller_key
),
rev AS (
    SELECT f.seller_key,
           sum(f.item_revenue) FILTER (WHERE os.order_status NOT IN ('canceled','unavailable')) AS revenue,
           sum(f.quantity)     AS units
    FROM dw.fact_sales f
    JOIN dw.dim_order_status os ON os.order_status_key = f.order_status_key
    GROUP BY f.seller_key
),
ful AS (
    SELECT so.seller_key,
           count(*)                                AS orders,
           count(*) FILTER (WHERE o.is_delivered)  AS delivered_orders,
           count(*) FILTER (WHERE o.is_late)       AS late_orders,
           avg(o.delivery_days)                    AS avg_delivery_days
    FROM seller_orders so
    JOIN dw.fact_order_fulfillment o ON o.order_id = so.order_id
    GROUP BY so.seller_key
),
rv AS (
    SELECT so.seller_key, count(*) AS reviews, avg(r.review_score) AS avg_review_score
    FROM seller_orders so
    JOIN dw.fact_review r ON r.order_id = so.order_id
    GROUP BY so.seller_key
)
SELECT
    s.seller_id,
    g.state_code AS seller_state, g.region AS seller_region, g.city AS seller_city,
    coalesce(rev.revenue, 0)  AS revenue,
    rev.units,
    ful.orders, ful.delivered_orders, ful.late_orders,
    round(ful.late_orders::numeric / nullif(ful.delivered_orders, 0), 4) AS late_rate,
    round(ful.avg_delivery_days, 2) AS avg_delivery_days,
    rv.reviews,
    round(rv.avg_review_score, 2)   AS avg_review_score
FROM dw.dim_seller s
JOIN dw.dim_geography g ON g.geography_key = s.geography_key
JOIN ful ON ful.seller_key = s.seller_key
LEFT JOIN rev ON rev.seller_key = s.seller_key
LEFT JOIN rv  ON rv.seller_key  = s.seller_key
WHERE s.seller_key <> -1;
CREATE INDEX ON olap.mv_seller_scorecard (seller_state);
