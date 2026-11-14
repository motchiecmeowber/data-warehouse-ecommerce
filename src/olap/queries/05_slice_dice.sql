-- SLICE: cố định 1 chiều (năm = 2017), xem theo các chiều còn lại.
SELECT category, sum(item_revenue) AS revenue
FROM olap.v_sales
WHERE is_valid_sale AND year = 2017
GROUP BY category ORDER BY revenue DESC LIMIT 10;

-- DICE: chọn tập con trên nhiều chiều (năm 2017-2018, vùng Sudeste/Sul, 3 danh mục) rồi tổng hợp theo tháng.
SELECT year_month, sum(item_revenue) AS revenue, sum(quantity) AS units
FROM olap.v_sales
WHERE is_valid_sale
  AND year IN (2017, 2018)
  AND customer_region IN ('Sudeste', 'Sul')
  AND category IN ('health_beauty', 'bed_bath_table', 'sports_leisure')
GROUP BY year_month ORDER BY year_month;
