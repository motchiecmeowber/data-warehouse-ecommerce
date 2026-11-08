"""
Khảo sát bước 5 – Giá trị hợp lệ và nhất quán: kiểu dữ liệu, mốc thời gian vô lý,
miền giá trị số, tọa độ, cách viết tên, khoảng trắng thừa.
Chạy (ở thư mục gốc): python -m src.profiling.step5_validity
"""
import pandas as pd

from src.profiling.load import load_all

DATE_COLS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}
TEXT_COLS = {
    "customers": ["customer_city", "customer_state"],
    "sellers": ["seller_city", "seller_state"],
    "geolocation": ["geolocation_city", "geolocation_state"],
    "products": ["product_category_name"],
}

if __name__ == "__main__":
    df = load_all()

    print("=== 1. Cột ngày giờ: giá trị không ép được kiểu, min, max ===")
    for table, cols in DATE_COLS.items():
        for c in cols:
            raw = df[table][c]
            parsed = pd.to_datetime(raw, errors="coerce")
            bad = raw.notna() & parsed.isna()
            print(f"{table}.{c}: lỗi kiểu={bad.sum()}, min={parsed.min()}, max={parsed.max()}")
            df[table][c] = parsed

    print("\n=== 2. Thứ tự mốc thời gian của đơn (số đơn vi phạm) ===")
    o = df["orders"]
    checks = {
        "duyệt trước khi đặt": o.order_approved_at < o.order_purchase_timestamp,
        "giao vận chuyển trước khi đặt": o.order_delivered_carrier_date < o.order_purchase_timestamp,
        "giao vận chuyển trước khi duyệt": o.order_delivered_carrier_date < o.order_approved_at,
        "khách nhận trước khi giao vận chuyển": o.order_delivered_customer_date < o.order_delivered_carrier_date,
        "khách nhận trước khi đặt": o.order_delivered_customer_date < o.order_purchase_timestamp,
        "ngày hẹn giao trước ngày đặt": o.order_estimated_delivery_date < o.order_purchase_timestamp,
        "trạng thái khác delivered nhưng có ngày khách nhận":
            (o.order_status != "delivered") & o.order_delivered_customer_date.notna(),
    }
    for name, mask in checks.items():
        print(f"{name}: {mask.sum()}")

    i = df["order_items"]
    print(f"shipping_limit_date sau 2018-12-31: {(i.shipping_limit_date > '2018-12-31').sum()}")

    print("\n=== 3. Miền giá trị số ===")
    print(i[["price", "freight_value"]].describe().round(2).to_string())
    print(f"price <= 0: {(i.price <= 0).sum()}, freight_value = 0: {(i.freight_value == 0).sum()}")
    p = df["order_payments"]
    print(p[["payment_installments", "payment_value"]].describe().round(2).to_string())
    print(f"payment_value = 0: {(p.payment_value == 0).sum()}, installments = 0: {(p.payment_installments == 0).sum()}")
    print("payment_type:", p.payment_type.value_counts().to_dict())
    print("review_score:", df["order_reviews"].review_score.value_counts().sort_index().to_dict())
    pr = df["products"]
    print(f"product_weight_g = 0: {(pr.product_weight_g == 0).sum()}")

    print("\n=== 4. Tọa độ geolocation nằm ngoài lãnh thổ Brazil ===")
    g = df["geolocation"]
    outside = (g.geolocation_lat > 5.3) | (g.geolocation_lat < -33.8) | (g.geolocation_lng > -34.7) | (g.geolocation_lng < -74.0)
    print(f"{outside.sum()} dòng")

    print("\n=== 5. Chữ: khoảng trắng thừa, chữ hoa, có dấu ===")
    for table, cols in TEXT_COLS.items():
        for c in cols:
            s = df[table][c].dropna()
            print(f"{table}.{c}: khoảng trắng thừa={(s != s.str.strip()).sum()}, "
                  f"có chữ hoa={(s != s.str.lower()).sum() if 'state' not in c else '-'}, "
                  f"có dấu={s.str.contains(r'[^\x00-\x7F]').sum()}")

    print("\n=== 6. Mã bang ===")
    for table, c in [("customers", "customer_state"), ("sellers", "seller_state"), ("geolocation", "geolocation_state")]:
        print(f"{table}.{c}: {df[table][c].nunique()} giá trị")

    print("\n=== 7. Mã bưu điện thuộc nhiều bang / nhiều cách viết tên thành phố ===")
    print(f"mã thuộc nhiều bang: {(g.groupby('geolocation_zip_code_prefix').geolocation_state.nunique() > 1).sum()}")
    print(f"mã có nhiều cách viết tên thành phố: {(g.groupby('geolocation_zip_code_prefix').geolocation_city.nunique() > 1).sum()}")
