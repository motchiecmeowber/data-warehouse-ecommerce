-- fact_payment: 1 dòng = 1 lần thanh toán của 1 đơn.
-- staging.order_payments_typed đã ép kiểu (R37) và áp R26, R27, R28.

INSERT INTO dw.fact_payment (
    order_id, payment_sequential, customer_key, purchase_date_key, payment_type_key,
    payment_installments, payment_value
)
SELECT
    p.order_id,
    p.payment_sequential,
    k.customer_key,
    k.purchase_date_key,
    coalesce(t.payment_type_key, -1),
    p.payment_installments,
    p.payment_value
FROM staging.order_payments_typed p
JOIN staging.order_keys k ON k.order_id = p.order_id                  -- R36
LEFT JOIN dw.dim_payment_type t ON t.payment_type = p.payment_type
WHERE p.payment_sequential IS NOT NULL                                -- R37: thiếu khóa -> không nạp
ORDER BY p.order_id, p.payment_sequential;
