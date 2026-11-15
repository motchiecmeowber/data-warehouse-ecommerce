-- Logistics: tỷ lệ trễ và thời gian giao theo tuyến (bang người bán -> bang khách), tuyến có >= 30 đơn đã giao.
SELECT route, route_type,
       count(*) AS delivered_orders,
       round(avg(is_late::int), 4)  AS late_rate,
       round(avg(delivery_days), 1) AS avg_delivery_days,
       round(avg(promised_days), 1) AS avg_promised_days,
       round(avg(distance_km), 0)   AS avg_distance_km
FROM olap.v_fulfillment
WHERE is_delivered AND route IS NOT NULL
GROUP BY route, route_type
HAVING count(*) >= 30
ORDER BY late_rate DESC LIMIT 20;

-- Tỷ lệ trễ theo thời điểm: ngày thường / cuối tuần / lễ / Black Friday
SELECT
    CASE WHEN is_black_friday THEN 'Black Friday' WHEN is_holiday THEN 'Ngày lễ'
         WHEN is_weekend THEN 'Cuối tuần' ELSE 'Ngày thường' END AS day_type,
    count(*) AS delivered_orders, round(avg(is_late::int), 4) AS late_rate
FROM olap.v_fulfillment WHERE is_delivered
GROUP BY 1 ORDER BY late_rate DESC;
