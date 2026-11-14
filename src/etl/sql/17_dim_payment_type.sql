-- dim_payment_type: các loại thanh toán có trong dữ liệu (staging.order_payments_typed đã áp R27).

INSERT INTO dw.dim_payment_type (payment_type)
SELECT DISTINCT payment_type
FROM staging.order_payments_typed
WHERE payment_type IS NOT NULL
ORDER BY payment_type;
