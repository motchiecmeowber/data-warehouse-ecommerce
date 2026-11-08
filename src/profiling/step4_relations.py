"""
Khảo sát bước 4 – Quan hệ: khóa ngoại giữa các bảng có khớp không (bản ghi mồ côi).
Chạy (ở thư mục gốc): python -m src.profiling.step4_relations
"""
from src.profiling.load import load_all

# (bảng con, cột, bảng cha, cột)
RELATIONS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("order_payments", "order_id", "orders", "order_id"),
    ("order_reviews", "order_id", "orders", "order_id"),
    ("products", "product_category_name", "product_category_name_translation", "product_category_name"),
    ("customers", "customer_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
    ("sellers", "seller_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
]

# (bảng cha, cột, bảng con, cột): bản ghi cha không có bản ghi con nào
MISSING_CHILDREN = [
    ("orders", "order_id", "order_items", "order_id"),
    ("orders", "order_id", "order_payments", "order_id"),
    ("orders", "order_id", "order_reviews", "order_id"),
]

if __name__ == "__main__":
    df = load_all()

    print("=== Bản ghi con không tìm thấy bản ghi cha ===")
    for child, ccol, parent, pcol in RELATIONS:
        values = df[child][ccol].dropna()
        orphans = values[~values.isin(df[parent][pcol])]
        print(f"{child}.{ccol} -> {parent}.{pcol}: {len(orphans)} dòng mồ côi ({orphans.nunique()} giá trị khác nhau)")
        if 0 < orphans.nunique() <= 5:
            print(f"   giá trị: {sorted(orphans.unique().tolist())}")

    print("\n=== Bản ghi cha không có bản ghi con ===")
    for parent, pcol, child, ccol in MISSING_CHILDREN:
        missing = ~df[parent][pcol].isin(df[child][ccol])
        print(f"{parent} không có {child}: {missing.sum()}")
