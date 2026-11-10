-- Kiểm tra chất lượng sau khi nạp: mỗi phép kiểm tra so giá trị mong đợi với giá trị thực tế.
-- Đạt khi expected = actual (cột passed tự tính). Kết quả ghi vào etl_log.quality_check.
-- Khóa chính, khóa ngoại, CHECK đã do database chặn khi nạp nên không kiểm tra lại ở đây.

INSERT INTO etl_log.quality_check (run_id, category, check_name, expected, actual)
SELECT current_setting('etl.run_id')::int, category, check_name, expected, actual
FROM (VALUES
    -- 1. Đầy đủ: số dòng trong kho khớp với nguồn
    --    (đã trừ các dòng bị loại có chủ đích: đơn thiếu ngày đặt R36, thiếu giá / thiếu khóa R37)
    ('completeness', 'fact_order_fulfillment: 1 dòng mỗi đơn',
        (SELECT count(*) FROM staging.order_keys),
        (SELECT count(*) FROM dw.fact_order_fulfillment)),
    ('completeness', 'fact_sales: tổng quantity = số dòng order_items',
        (SELECT count(*) FROM staging.order_items_typed i JOIN staging.order_keys k USING (order_id)
         WHERE i.price IS NOT NULL),
        (SELECT sum(quantity) FROM dw.fact_sales)),
    ('completeness', 'fact_payment: 1 dòng mỗi lần thanh toán',
        (SELECT count(*) FROM staging.order_payments_typed p JOIN staging.order_keys k USING (order_id)
         WHERE p.payment_sequential IS NOT NULL),
        (SELECT count(*) FROM dw.fact_payment)),
    ('completeness', 'fact_review: 1 dòng mỗi đơn có review (R13)',
        (SELECT count(DISTINCT r.order_id) FROM staging.order_reviews r JOIN staging.order_keys k USING (order_id)),
        (SELECT count(*) FROM dw.fact_review)),
    ('completeness', 'dim_customer: đủ khách (customer_unique_id) có ít nhất 1 đơn có ngày đặt',
        (SELECT count(DISTINCT c.customer_unique_id)
         FROM staging.customers c
         JOIN staging.orders_typed o ON o.customer_id = c.customer_id
         WHERE o.order_purchase_timestamp IS NOT NULL),
        (SELECT count(DISTINCT customer_unique_id) FROM dw.dim_customer WHERE customer_key > 0)),
    ('completeness', 'dim_product: đủ sản phẩm',
        (SELECT count(DISTINCT product_id) FROM staging.products),
        (SELECT count(*) FROM dw.dim_product WHERE product_key > 0)),
    ('completeness', 'dim_seller: đủ người bán',
        (SELECT count(DISTINCT seller_id) FROM staging.sellers),
        (SELECT count(*) FROM dw.dim_seller WHERE seller_key > 0)),

    -- 2. Đối soát: tổng tiền trong kho khớp với nguồn
    ('reconciliation', 'Doanh thu: sum(item_revenue) = sum(price) nguồn',
        (SELECT sum(i.price) FROM staging.order_items_typed i JOIN staging.order_keys k USING (order_id)),
        (SELECT sum(item_revenue) FROM dw.fact_sales)),
    ('reconciliation', 'Phí vận chuyển: sum(freight_total) = sum(freight_value) nguồn',
        (SELECT sum(i.freight_value) FROM staging.order_items_typed i JOIN staging.order_keys k USING (order_id)
         WHERE i.price IS NOT NULL),
        (SELECT sum(freight_total) FROM dw.fact_sales)),
    ('reconciliation', 'Thanh toán: sum(payment_value) = nguồn',
        (SELECT sum(p.payment_value) FROM staging.order_payments_typed p JOIN staging.order_keys k USING (order_id)
         WHERE p.payment_sequential IS NOT NULL),
        (SELECT sum(payment_value) FROM dw.fact_payment)),
    ('reconciliation', 'Doanh thu theo đơn = doanh thu theo sản phẩm',
        (SELECT sum(item_revenue) FROM dw.fact_sales),
        (SELECT sum(order_revenue) FROM dw.fact_order_fulfillment)),

    -- 3. Khóa: fact không phải trỏ về Unknown (-1) khi nguồn có đủ thông tin
    ('referential', 'Fact trỏ customer_key = -1',
        0,
        (SELECT (SELECT count(*) FROM dw.fact_sales WHERE customer_key = -1)
              + (SELECT count(*) FROM dw.fact_order_fulfillment WHERE customer_key = -1)
              + (SELECT count(*) FROM dw.fact_payment WHERE customer_key = -1)
              + (SELECT count(*) FROM dw.fact_review WHERE customer_key = -1))),
    ('referential', 'fact_sales trỏ product_key hoặc seller_key = -1',
        0,
        (SELECT count(*) FROM dw.fact_sales WHERE product_key = -1 OR seller_key = -1)),
    ('referential', 'Ngày đặt nằm ngoài dim_date (purchase_date_key = -1)',
        0,
        (SELECT count(*) FROM dw.fact_order_fulfillment WHERE purchase_date_key = -1)),

    -- 4. SCD2: mỗi khách đúng 1 phiên bản hiện tại, các phiên bản nối tiếp không chồng lấn
    ('scd2', 'Khách không có đúng 1 phiên bản hiện tại',
        0,
        (SELECT count(*) FROM (
            SELECT customer_unique_id FROM dw.dim_customer WHERE customer_key > 0
            GROUP BY customer_unique_id HAVING count(*) FILTER (WHERE is_current) <> 1) x)),
    ('scd2', 'Phiên bản có valid_to khác valid_from của phiên bản kế tiếp',
        0,
        (SELECT count(*) FROM (
            SELECT valid_to, lead(valid_from, 1, TIMESTAMP '9999-12-31')
                       OVER (PARTITION BY customer_unique_id ORDER BY "version") AS next_from
            FROM dw.dim_customer WHERE customer_key > 0) x
         WHERE valid_to <> next_from)),

    -- 5. Hợp lệ: giá trị đúng quy tắc
    ('validity', 'is_late chỉ null khi đơn chưa giao (R04)',
        0,
        (SELECT count(*) FROM dw.fact_order_fulfillment WHERE (is_late IS NULL) <> (NOT is_delivered))),
    ('validity', 'Mã bưu điện không tra được tên bang',
        0,
        (SELECT count(*) FROM dw.dim_geography WHERE geography_key > 0 AND state_name IS NULL)),
    ('validity', 'Sản phẩm thiếu tên danh mục tiếng Anh (R17)',
        0,
        (SELECT count(*) FROM dw.dim_product WHERE product_key > 0 AND category_name_en IS NULL))
) AS c(category, check_name, expected, actual);