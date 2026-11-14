-- ROLL-UP: doanh thu theo Năm -> Quý -> Tháng, có dòng tổng cấp trên (ROLLUP).
-- grouping() = 1 cho biết cột đó đã bị gộp (dòng subtotal / grand total).
SELECT
    year, quarter, month,
    grouping(year, quarter, month)  AS grp_level,   -- 0 = chi tiết tháng, 1 = tổng quý, 3 = tổng năm, 7 = tổng cộng
    sum(item_revenue)               AS revenue,
    sum(quantity)                   AS units
FROM olap.v_sales
WHERE is_valid_sale
GROUP BY ROLLUP (year, quarter, month)
ORDER BY year, quarter, month;
