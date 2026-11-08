"""
Khảo sát bước 2 – Thiếu dữ liệu: số và tỷ lệ giá trị null của từng cột (chỉ in cột có null).
Chạy (ở thư mục gốc): python -m src.profiling.step2_missing
"""
import pandas as pd

from src.profiling.load import load_all

if __name__ == "__main__":
    df = load_all()
    for name, d in df.items():
        na = d.isna().sum()
        na = na[na > 0]
        print(f"-- {name} ({len(d)} dòng)")
        if na.empty:
            print("   không có null\n")
            continue
        print(pd.DataFrame({"so_null": na, "ty_le_%": (na / len(d) * 100).round(2)}).to_string(), "\n")

    # Null ở các mốc thời gian của đơn, tách theo trạng thái đơn
    o = df["orders"]
    date_cols = ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date"]
    print("=== orders: số null mỗi mốc thời gian theo trạng thái ===")
    print(o[date_cols].isna().groupby(o["order_status"]).sum().assign(so_don=o["order_status"].value_counts()).to_string(), "\n")

    # products: mỗi dòng thiếu bao nhiêu cột trong từng nhóm cột
    p = df["products"]
    groups = {
        "nhom_mo_ta": ["product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty"],
        "nhom_kich_thuoc": ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
    }
    for group, cols in groups.items():
        print(f"=== products – {group}: số dòng theo số cột bị null (0..4) ===")
        print(p[cols].isna().sum(axis=1).value_counts().sort_index().to_string(), "\n")