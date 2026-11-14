-- KPI toàn kho (đơn hợp lệ = không hủy / không có hàng)
-- Doanh thu, số đơn, giá trị đơn trung bình (AOV), tỷ lệ phí vận chuyển, tỷ lệ giao trễ, thời gian giao, điểm review
SELECT
    sum(order_revenue)  FILTER (WHERE is_valid_sale)                                     AS revenue,
    count(*)            FILTER (WHERE is_valid_sale)                                     AS orders,
    round(sum(order_revenue) FILTER (WHERE is_valid_sale)
          / nullif(count(*) FILTER (WHERE is_valid_sale), 0), 2)   AS avg_order_value,
    round(sum(order_freight) FILTER (WHERE is_valid_sale)
          / nullif(sum(order_revenue) FILTER (WHERE is_valid_sale), 0), 4)               AS freight_ratio,
    round(avg(is_late::int) FILTER (WHERE is_delivered), 4)                              AS late_rate,
    round(avg(delivery_days) FILTER (WHERE is_delivered), 2)                             AS avg_delivery_days,
    (SELECT round(avg(review_score), 2) FROM olap.v_review)                              AS avg_review_score
FROM olap.v_fulfillment;
