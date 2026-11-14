-- Top 10 người bán theo doanh thu, kèm tỷ lệ trễ và điểm review (materialized view scorecard)
SELECT seller_id, seller_state, revenue, orders, late_rate, avg_review_score
FROM olap.mv_seller_scorecard ORDER BY revenue DESC LIMIT 10;

-- Thanh toán: cơ cấu theo loại và số kỳ trả góp trung bình
SELECT payment_type, count(*) AS payments, sum(payment_value) AS value,
       round(avg(payment_installments), 2) AS avg_installments
FROM olap.v_payment GROUP BY payment_type ORDER BY value DESC;

-- Review: điểm trung bình theo giao đúng hạn / trễ (drill-across fact_review với fact_order_fulfillment qua order_id)
SELECT CASE WHEN o.is_late THEN 'Giao trễ' ELSE 'Đúng hạn / sớm' END AS delivery,
       count(*) AS reviews, round(avg(r.review_score), 2) AS avg_score
FROM olap.v_review r JOIN olap.v_fulfillment o USING (order_id)
WHERE o.is_delivered
GROUP BY 1;
