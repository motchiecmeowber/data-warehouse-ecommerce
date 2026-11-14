-- PIVOT (bảng tổng hợp chéo): doanh thu theo Danh mục (hàng) x Quý của năm 2017 (cột), dùng FILTER.
SELECT
    category,
    sum(item_revenue) FILTER (WHERE quarter = 1) AS q1,
    sum(item_revenue) FILTER (WHERE quarter = 2) AS q2,
    sum(item_revenue) FILTER (WHERE quarter = 3) AS q3,
    sum(item_revenue) FILTER (WHERE quarter = 4) AS q4,
    sum(item_revenue)                            AS total
FROM olap.v_sales
WHERE is_valid_sale AND year = 2017
GROUP BY category ORDER BY total DESC LIMIT 15;

-- PIVOT 2: tỷ lệ giao trễ theo Vùng khách (hàng) x Loại tuyến (cột)
SELECT
    customer_region,
    round(avg(is_late::int) FILTER (WHERE route_type = 'Cùng bang'), 4)  AS late_rate_same_state,
    round(avg(is_late::int) FILTER (WHERE route_type = 'Khác bang'), 4)  AS late_rate_cross_state
FROM olap.v_fulfillment
WHERE is_delivered
GROUP BY customer_region ORDER BY customer_region;
