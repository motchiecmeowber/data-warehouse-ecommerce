-- dim_payment_type: các loại thanh toán có trong dữ liệu.

INSERT INTO dw.dim_payment_type (payment_type)
SELECT DISTINCT
    CASE WHEN payment_type = 'not_defined' THEN 'unknown' ELSE payment_type END   -- R27
FROM staging.order_payments
WHERE payment_type IS NOT NULL
ORDER BY 1;