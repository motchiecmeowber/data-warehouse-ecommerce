"""
Khảo sát bước 6 – Phân phối: số đơn theo tháng, theo trạng thái, theo bang; tỷ lệ giao trễ.
Chạy (ở thư mục gốc): python -m src.profiling.step6_distribution
"""
import pandas as pd

from src.profiling.load import load_all

if __name__ == "__main__":
    df = load_all()
    o = df["orders"].copy()
    for c in ["order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]:
        o[c] = pd.to_datetime(o[c])
    o["month"] = o.order_purchase_timestamp.dt.to_period("M")

    print("=== Số đơn theo trạng thái ===")
    print(o.order_status.value_counts().to_string(), "\n")

    delivered = o[(o.order_status == "delivered") & o.order_delivered_customer_date.notna()].copy()
    delivered["is_late"] = delivered.order_delivered_customer_date.dt.normalize() > delivered.order_estimated_delivery_date

    print("=== Theo tháng: số đơn, số đơn đã giao, tỷ lệ trễ (%) ===")
    by_month = pd.DataFrame({
        "so_don": o.groupby("month").size(),
        "da_giao": delivered.groupby("month").size(),
        "tre_%": (delivered.groupby("month").is_late.mean() * 100).round(1),
    }).fillna(0)
    print(by_month.to_string(), "\n")

    print(f"Tỷ lệ trễ toàn bộ: {delivered.is_late.mean() * 100:.2f}% trên {len(delivered)} đơn đã giao\n")

    c = df["customers"]
    state = delivered.merge(c[["customer_id", "customer_state"]], on="customer_id")
    print("=== Theo bang của khách: số đơn đã giao, tỷ lệ trễ (%) ===")
    print(state.groupby("customer_state").agg(
        so_don=("order_id", "size"), tre_pct=("is_late", lambda s: round(s.mean() * 100, 1))
    ).sort_values("so_don", ascending=False).to_string(), "\n")

    print("=== Số đơn mỗi khách (customer_unique_id) ===")
    per_customer = o.merge(c[["customer_id", "customer_unique_id"]], on="customer_id").groupby("customer_unique_id").size()
    print(per_customer.value_counts().sort_index().to_string())
    print(f"Khách mua từ 2 đơn trở lên: {(per_customer > 1).mean() * 100:.2f}%")
