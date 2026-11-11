"""Đọc đơn đã giao từ DW, tính RFM và chia khách thành 5 nhóm bằng K-Means."""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


logger = logging.getLogger(__name__)

QUERY = """
    SELECT
        orders.order_id,
        customers.customer_unique_id,
        orders.order_purchase_timestamp,
        orders.order_revenue
    FROM dw.fact_order_fulfillment AS orders
    JOIN dw.dim_customer AS customers
        ON customers.customer_key = orders.customer_key
    JOIN dw.dim_order_status AS statuses
        ON statuses.order_status_key = orders.order_status_key
    WHERE statuses.order_status = 'delivered'
      AND customers.customer_unique_id IS NOT NULL
"""


def load_orders(connection):
    """Mỗi đơn đã giao một dòng: order_id, khách, ngày mua, tiền hàng."""
    orders = pd.read_sql_query(QUERY, connection)
    return validate_orders(orders)


def validate_orders(orders):
    """Kiểm tra khóa, ngày mua và tiền hàng trước khi tính RFM."""
    orders = orders.copy()

    if orders.empty:
        raise ValueError("Không có đơn đã giao nào trong DW")

    for column in ["order_id", "customer_unique_id"]:
        orders[column] = orders[column].astype("string").str.strip().replace("", pd.NA)
    orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
    orders["order_revenue"] = pd.to_numeric(orders["order_revenue"]).astype(float)

    if orders.isna().any().any():
        raise ValueError("Đơn hàng thiếu ID, ngày mua hoặc tiền hàng")

    if not np.isfinite(orders["order_revenue"]).all() or orders["order_revenue"].le(0).any():
        raise ValueError("Tiền hàng phải hữu hạn và lớn hơn 0")

    if orders["order_id"].duplicated().any():
        raise ValueError("Một đơn bị lặp nhiều dòng, tiền hàng sẽ bị cộng đôi")

    return orders


def build_rfm(orders):
    """Mỗi khách một dòng: recency_days, frequency, monetary, avg_order_value."""
    # Mốc tính recency = ngày mua cuối cùng trong dữ liệu + 1 ngày.
    reference_date = orders["order_purchase_timestamp"].max().normalize() + pd.Timedelta(days=1)

    rfm = orders.groupby("customer_unique_id").agg(
        last_purchase=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("order_revenue", "sum"),
    )
    rfm["recency_days"] = (reference_date - rfm["last_purchase"].dt.normalize()).dt.days
    rfm["avg_order_value"] = rfm["monetary"] / rfm["frequency"]

    return rfm[["recency_days", "frequency", "monetary", "avg_order_value"]]


def fit_features(rfm):
    """Cắt đuôi P99, log1p rồi chuẩn hóa. Recency được đảo để mua gần = giá trị cao."""
    columns = ["frequency", "monetary"]
    caps = rfm[columns].quantile(0.99)
    capped = rfm[columns].clip(upper=caps, axis="columns")

    features = np.log1p(capped)
    features["recency_inverted"] = np.log1p(rfm["recency_days"].max() - rfm["recency_days"] + 1e-6)
    features = features[["recency_inverted", "frequency", "monetary"]]

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    preprocessing = {
        "scaler": scaler,
        "caps": caps.to_dict(),
        "max_recency": float(rfm["recency_days"].max()),
        "features": list(features.columns),
    }
    return scaled, preprocessing


def scale_features(rfm):
    """Trả về cùng ma trận chuẩn hóa cho luồng K-Means hiện có."""
    scaled, _ = fit_features(rfm)
    return scaled


def name_clusters(rfm):
    """Đặt tên cho từng cụm dựa trên trung vị RFM của cụm."""
    profile = rfm.groupby("kmeans_cluster")[["recency_days", "frequency", "monetary"]].median()

    recent_limit, inactive_limit = rfm["recency_days"].quantile([0.5, 0.9])
    low_limit, high_limit = rfm["monetary"].quantile([0.25, 0.75])

    # Điều kiện đứng sau sẽ ghi đè điều kiện đứng trước.
    labels = pd.Series("Chi tiêu tầm trung", index=profile.index)
    labels[profile["recency_days"] < recent_limit] = "Mua gần hơn, chi tiêu tầm trung"
    labels[profile["monetary"] < low_limit] = "Chi tiêu thấp"
    labels[profile["monetary"] > high_limit] = "Chi tiêu cao"
    labels[profile["recency_days"] > inactive_limit] = "Lâu chưa mua"
    labels[profile["frequency"] > 1] = "Khách mua lại"

    return labels


def save_csv(rfm, output_path):
    """Ghi ra file tạm rồi mới thay file đích, để lỗi giữa chừng không làm hỏng file cũ."""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(dir=output_path.parent, suffix=".csv", delete=False) as temporary:
        temp_path = Path(temporary.name)

    try:
        rfm.to_csv(temp_path, index_label="customer_unique_id", encoding="utf-8-sig")
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)

    return output_path


def run_kmeans(connection, output_path="output/kmeans/customer_segments.csv"):
    """Đọc DW, tính RFM, phân 5 cụm, gán tên và trả đường dẫn CSV."""
    orders = load_orders(connection)
    logger.info("Đã đọc %s đơn đã giao", len(orders))

    rfm = build_rfm(orders)
    scaled_features = scale_features(rfm)

    model = KMeans(n_clusters=5, random_state=42, n_init=10)
    rfm["kmeans_cluster"] = model.fit_predict(scaled_features)
    rfm["kmeans_segment"] = rfm["kmeans_cluster"].map(name_clusters(rfm))
    logger.info("Phân bố nhóm:\n%s", rfm["kmeans_segment"].value_counts().to_string())

    saved_path = save_csv(rfm, output_path)
    logger.info("Đã lưu %s khách vào %s", len(rfm), saved_path)

    return saved_path


if __name__ == "__main__":
    from src.common.db import get_engine

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    engine = get_engine()
    try:
        run_kmeans(engine)
    finally:
        engine.dispose()
