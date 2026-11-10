-- dim_order_status: các trạng thái đơn có trong dữ liệu.

INSERT INTO dw.dim_order_status (order_status)
SELECT DISTINCT order_status
FROM staging.orders
WHERE order_status IS NOT NULL
ORDER BY order_status;