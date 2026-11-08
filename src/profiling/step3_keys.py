"""
Khảo sát bước 3 – Khóa và trùng lặp: cột/cặp cột nào duy nhất, dòng nào bị trùng.
Chạy (ở thư mục gốc): python -m src.profiling.step3_keys
"""
from src.profiling.load import load_all

# (bảng, các cột dự kiến là khóa)
CANDIDATE_KEYS = [
    ("orders", ["order_id"]),
    ("customers", ["customer_id"]),
    ("customers", ["customer_unique_id"]),
    ("sellers", ["seller_id"]),
    ("products", ["product_id"]),
    ("order_items", ["order_id", "order_item_id"]),
    ("order_payments", ["order_id", "payment_sequential"]),
    ("order_reviews", ["review_id"]),
    ("order_reviews", ["order_id"]),
    ("order_reviews", ["review_id", "order_id"]),
    ("geolocation", ["geolocation_zip_code_prefix"]),
    ("product_category_name_translation", ["product_category_name"]),
]

if __name__ == "__main__":
    df = load_all()

    print("=== Kiểm tra khóa ===")
    for table, cols in CANDIDATE_KEYS:
        d = df[table]
        dup = d.duplicated(cols).sum()
        status = "duy nhất" if dup == 0 else f"TRÙNG {dup} dòng"
        print(f"{table}.{'+'.join(cols)}: {d[cols].drop_duplicates().shape[0]} giá trị khác nhau / {len(d)} dòng -> {status}")

    print("\n=== Dòng trùng hoàn toàn (mọi cột giống nhau) ===")
    for name, d in df.items():
        print(f"{name}: {d.duplicated().sum()}")
