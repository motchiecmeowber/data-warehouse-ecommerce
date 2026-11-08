# Sơ đồ kho dữ liệu

Star schema, riêng nhánh địa lý tách bảng (`dim_geography` dùng chung cho khách và người bán). Chi tiết cột: [data_dictionary.md](../data_dictionary.md).

GitHub hiển thị sơ đồ Mermaid trực tiếp khi mở file này.

```mermaid
erDiagram
    dim_geography ||--o{ dim_customer : "geography_key"
    dim_geography ||--o{ dim_seller : "geography_key"

    dim_date ||--o{ fact_sales : "purchase_date_key"
    dim_customer ||--o{ fact_sales : "customer_key"
    dim_product ||--o{ fact_sales : "product_key"
    dim_seller ||--o{ fact_sales : "seller_key"
    dim_order_status ||--o{ fact_sales : "order_status_key"

    dim_date ||--o{ fact_order_fulfillment : "5 vai: purchase, approved, carrier, delivered, estimated"
    dim_customer ||--o{ fact_order_fulfillment : "customer_key"
    dim_order_status ||--o{ fact_order_fulfillment : "order_status_key"

    dim_date ||--o{ fact_payment : "purchase_date_key"
    dim_customer ||--o{ fact_payment : "customer_key"
    dim_payment_type ||--o{ fact_payment : "payment_type_key"

    dim_date ||--o{ fact_review : "2 vai: creation, answer"
    dim_customer ||--o{ fact_review : "customer_key"

    dim_geography {
        int geography_key PK
        char zip_code_prefix UK
        text city
        char state_code
        text state_name
        text region
        numeric latitude
        numeric longitude
        bool has_coordinates
    }
    dim_customer {
        int customer_key PK
        char customer_unique_id
        int geography_key FK
        timestamp valid_from
        timestamp valid_to
        bool is_current
        smallint version
    }
    dim_seller {
        int seller_key PK
        char seller_id UK
        int geography_key FK
    }
    dim_product {
        int product_key PK
        char product_id UK
        text category_name
        text category_name_en
        int name_length
        int description_length
        int photos_qty
        numeric weight_g
        numeric length_cm
        numeric height_cm
        numeric width_cm
    }
    dim_date {
        int date_key PK
        date full_date
        smallint day
        smallint month
        smallint quarter
        smallint year
        smallint day_of_week
        bool is_weekend
        bool is_holiday
        bool is_black_friday
    }
    dim_order_status {
        smallint order_status_key PK
        text order_status UK
    }
    dim_payment_type {
        smallint payment_type_key PK
        text payment_type UK
    }
    fact_sales {
        char order_id PK
        int product_key PK
        int seller_key FK
        int customer_key FK
        smallint order_status_key FK
        int purchase_date_key FK
        int quantity
        numeric unit_price
        numeric item_revenue
        numeric freight_total
        numeric item_weight_g
        timestamp shipping_limit_date
        bool is_shipping_limit_anomaly
    }
    fact_order_fulfillment {
        char order_id PK
        int customer_key FK
        smallint order_status_key FK
        int purchase_date_key FK
        int approved_date_key FK
        int carrier_date_key FK
        int delivered_date_key FK
        int estimated_date_key FK
        timestamp order_purchase_timestamp
        int item_count
        smallint seller_count
        numeric order_revenue
        numeric order_freight
        numeric order_weight_g
        numeric approval_days
        numeric handling_days
        numeric transit_days
        numeric delivery_days
        numeric promised_days
        numeric delay_days
        bool is_delivered
        bool is_late
        bool has_missing_milestone
        bool has_time_anomaly
    }
    fact_payment {
        char order_id PK
        smallint payment_sequential PK
        int customer_key FK
        int purchase_date_key FK
        smallint payment_type_key FK
        smallint payment_installments
        numeric payment_value
    }
    fact_review {
        char review_id PK
        char order_id PK
        int customer_key FK
        int review_creation_date_key FK
        int review_answer_date_key FK
        smallint review_score
        bool has_comment
        numeric response_days
    }
```
