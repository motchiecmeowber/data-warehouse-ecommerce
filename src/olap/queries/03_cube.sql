-- CUBE: doanh thu theo mọi tổ hợp của Vùng khách hàng x Năm (cả tổng theo vùng, tổng theo năm, tổng cộng).
SELECT
    coalesce(customer_region, '(Tất cả vùng)')  AS customer_region,
    coalesce(year::text, '(Tất cả năm)')        AS year,
    sum(item_revenue)                           AS revenue,
    count(DISTINCT order_id)                    AS orders
FROM olap.v_sales
WHERE is_valid_sale
GROUP BY CUBE (customer_region, year)
ORDER BY grouping(customer_region, year), customer_region, year;

-- GROUPING SETS: chỉ lấy các tổ hợp cần thiết (rẻ hơn CUBE khi nhiều chiều)
SELECT customer_region, category, year, sum(item_revenue) AS revenue
FROM olap.v_sales
WHERE is_valid_sale
GROUP BY GROUPING SETS ((customer_region, year), (category, year), (year))
ORDER BY year, customer_region, category;
