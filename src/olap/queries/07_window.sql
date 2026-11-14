-- Tăng trưởng theo tháng (MoM) và doanh thu lũy kế (window function).
WITH monthly AS (
    SELECT year_month, sum(item_revenue) AS revenue
    FROM olap.v_sales WHERE is_valid_sale GROUP BY year_month
)
SELECT
    year_month, revenue,
    round((revenue / nullif(lag(revenue) OVER w, 0) - 1) * 100, 1) AS mom_growth_pct,
    sum(revenue) OVER (ORDER BY year_month)                         AS cumulative_revenue
FROM monthly
WINDOW w AS (ORDER BY year_month)
ORDER BY year_month;

-- Top 3 danh mục theo doanh thu trong từng vùng (RANK theo nhóm)
SELECT * FROM (
    SELECT customer_region, category, sum(item_revenue) AS revenue,
           rank() OVER (PARTITION BY customer_region ORDER BY sum(item_revenue) DESC) AS rnk
    FROM olap.v_sales WHERE is_valid_sale
    GROUP BY customer_region, category
) t WHERE rnk <= 3 ORDER BY customer_region, rnk;
