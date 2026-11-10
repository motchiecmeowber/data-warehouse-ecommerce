-- Fact: fact_sales (1 sản phẩm trong 1 đơn), fact_order_fulfillment (1 đơn, accumulating snapshot), fact_payment (1 lần thanh toán), fact_review (1 review của 1 đơn).

CREATE TABLE IF NOT EXISTS dw.fact_sales (
    order_id                    CHAR(32),
    product_key                 INTEGER NOT NULL REFERENCES dw.dim_product(product_key),
    seller_key                  INTEGER NOT NULL REFERENCES dw.dim_seller(seller_key),
    customer_key                INTEGER NOT NULL REFERENCES dw.dim_customer(customer_key),
    order_status_key            SMALLINT NOT NULL REFERENCES dw.dim_order_status(order_status_key),
    purchase_date_key           INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    quantity                    INTEGER NOT NULL CHECK (quantity >= 1),
    unit_price                  NUMERIC(10,2) NOT NULL,
    item_revenue                NUMERIC(12,2),
    freight_total               NUMERIC(12,2),
    item_weight_g               NUMERIC(12,2),
    shipping_limit_date         TIMESTAMP,
    is_shipping_limit_anomaly   BOOLEAN,
    PRIMARY KEY (order_id, product_key)
);

CREATE TABLE IF NOT EXISTS dw.fact_order_fulfillment (
    order_id                    CHAR(32) PRIMARY KEY,
    customer_key                INTEGER NOT NULL REFERENCES dw.dim_customer(customer_key),
    order_status_key            SMALLINT NOT NULL REFERENCES dw.dim_order_status(order_status_key),
    purchase_date_key           INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    approved_date_key           INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    carrier_date_key            INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    delivered_date_key          INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    estimated_date_key          INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    order_purchase_timestamp    TIMESTAMP NOT NULL,
    item_count                  INTEGER NOT NULL DEFAULT 0,
    seller_count                SMALLINT,
    order_revenue               NUMERIC(12,2),
    order_freight               NUMERIC(12,2),
    order_weight_g              NUMERIC(12,2),
    approval_days               NUMERIC(8,2),
    handling_days               NUMERIC(8,2),
    transit_days                NUMERIC(8,2),
    delivery_days               NUMERIC(8,2),
    promised_days               NUMERIC(8,2),
    delay_days                  NUMERIC(8,2),
    is_delivered                BOOLEAN,
    is_late                     BOOLEAN,
    has_missing_milestone       BOOLEAN,
    has_time_anomaly            BOOLEAN
);

CREATE TABLE IF NOT EXISTS dw.fact_payment (
    order_id                    CHAR(32),
    payment_sequential          SMALLINT,
    customer_key                INTEGER NOT NULL REFERENCES dw.dim_customer(customer_key),
    purchase_date_key           INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    payment_type_key            SMALLINT NOT NULL REFERENCES dw.dim_payment_type(payment_type_key),
    payment_installments        SMALLINT CHECK (payment_installments >= 1),
    payment_value               NUMERIC(12,2) CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS dw.fact_review (
    review_id                   CHAR(32),
    order_id                    CHAR(32),
    customer_key                INTEGER NOT NULL REFERENCES dw.dim_customer(customer_key),
    review_creation_date_key    INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    review_answer_date_key      INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    review_score                SMALLINT CHECK (review_score BETWEEN 1 AND 5),
    has_comment                 BOOLEAN,
    response_days               NUMERIC(8,2),
    PRIMARY KEY (review_id, order_id)
);