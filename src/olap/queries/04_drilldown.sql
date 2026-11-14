-- DRILL-DOWN theo chiều địa lý: Vùng -> Bang -> Thành phố (mỗi bước thêm 1 cấp chi tiết).

-- Cấp 1: vùng
SELECT customer_region, sum(item_revenue) AS revenue, count(DISTINCT order_id) AS orders
FROM olap.v_sales WHERE is_valid_sale
GROUP BY customer_region ORDER BY revenue DESC;

-- Cấp 2: các bang của vùng Sudeste
SELECT customer_region, customer_state, sum(item_revenue) AS revenue, count(DISTINCT order_id) AS orders
FROM olap.v_sales WHERE is_valid_sale AND customer_region = 'Sudeste'
GROUP BY customer_region, customer_state ORDER BY revenue DESC;

-- Cấp 3: các thành phố của bang SP (top 10)
SELECT customer_state, customer_city, sum(item_revenue) AS revenue, count(DISTINCT order_id) AS orders
FROM olap.v_sales WHERE is_valid_sale AND customer_state = 'SP'
GROUP BY customer_state, customer_city ORDER BY revenue DESC LIMIT 10;
