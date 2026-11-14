"""Đọc đơn đã giao từ DW, tính RFM và chia khách thành 4 nhóm bằng K-Means."""

import argparse
import logging
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text


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
      AND orders.order_purchase_timestamp >= :start_date
      AND orders.order_purchase_timestamp < :end_date
"""


def load_orders(connection, start_year, end_year):
    """Đọc toàn bộ đơn đã giao trong khoảng năm đã chọn."""
    if not 1 <= start_year <= end_year <= 9998:
        raise ValueError(
            "Năm phải thỏa 1 <= năm bắt đầu <= năm kết thúc <= 9998"
        )
    orders = pd.read_sql_query(
        text(QUERY),
        connection,
        params={
            "start_date": date(start_year, 1, 1),
            "end_date": date(end_year + 1, 1, 1),
        },
    )
    return validate_orders(orders)


def validate_orders(orders):
    """Kiểm tra khóa, ngày mua và tiền hàng trước khi tính RFM."""
    orders = orders.copy()

    if orders.empty:
        raise ValueError("Không có đơn đã giao nào trong DW")

    for column in ["order_id", "customer_unique_id"]:
        orders[column] = (
            orders[column].astype("string").str.strip().replace("", pd.NA)
        )
    orders["order_purchase_timestamp"] = pd.to_datetime(
        orders["order_purchase_timestamp"]
    )
    orders["order_revenue"] = pd.to_numeric(
        orders["order_revenue"]
    ).astype(float)

    if orders.isna().any().any():
        raise ValueError(
            "Đơn hàng thiếu ID, ngày mua hoặc tiền hàng"
        )

    revenue = orders["order_revenue"]
    if not np.isfinite(revenue).all() or revenue.lt(0).any():
        raise ValueError("Tiền hàng phải hữu hạn và không âm")

    if orders["order_id"].duplicated().any():
        raise ValueError("Một đơn bị lặp nhiều dòng, tiền hàng sẽ bị cộng đôi")

    orders = orders.loc[revenue.gt(0)].copy()
    if orders.empty:
        raise ValueError("Không có đơn đã giao có tiền hàng lớn hơn 0")
    return orders


def build_rfm(orders):
    """Tổng hợp Recency, Frequency, Monetary và giá trị đơn trung bình."""
    # Mốc tính recency = ngày mua cuối cùng trong dữ liệu + 1 ngày.
    reference_date = (
        orders["order_purchase_timestamp"].max().normalize()
        + pd.Timedelta(days=1)
    )

    rfm = orders.groupby("customer_unique_id").agg(
        last_purchase=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("order_revenue", "sum"),
    )
    last_purchase = rfm["last_purchase"].dt.normalize()
    rfm["recency_days"] = (reference_date - last_purchase).dt.days
    rfm["avg_order_value"] = rfm["monetary"] / rfm["frequency"]

    return rfm[["recency_days", "frequency", "monetary", "avg_order_value"]]


def scale_features(rfm):
    """Cắt P99, log1p, đảo Recency rồi chuẩn hóa ba đặc trưng RFM."""
    columns = ["frequency", "monetary"]
    caps = rfm[columns].quantile(0.99)
    capped = rfm[columns].clip(upper=caps, axis="columns")

    features = np.log1p(capped)
    features["recency_inverted"] = np.log1p(
        rfm["recency_days"].max() - rfm["recency_days"] + 1e-6
    )
    features = features[["recency_inverted", "frequency", "monetary"]]

    return StandardScaler().fit_transform(features)


def name_clusters(rfm):
    """Đặt tên theo trung vị RFM, ưu tiên mua lại rồi lâu chưa mua."""
    columns = ["recency_days", "frequency", "monetary"]
    profile = rfm.groupby("kmeans_cluster")[columns].median()
    labels = pd.Series(index=profile.index, dtype="string")

    repeat_cluster = profile["frequency"].idxmax()
    if profile.loc[repeat_cluster, "frequency"] > 1:
        labels[repeat_cluster] = "Khách mua lại"
    else:
        repeat_cluster = profile["monetary"].idxmax()
        labels[repeat_cluster] = "Khách chi tiêu cao nhất"
    remaining = profile.drop(index=repeat_cluster)

    inactive_cluster = remaining["recency_days"].idxmax()
    labels[inactive_cluster] = "Khách lâu chưa mua"
    remaining = remaining.drop(index=inactive_cluster)
    spending_order = remaining.sort_values("monetary", kind="stable").index
    labels[spending_order[0]] = "Khách chi tiêu thấp"
    labels[spending_order[1]] = "Khách chi tiêu cao"
    return labels


def save_csv(rfm, output_path):
    """Ghi file tạm rồi thay file đích để bảo toàn kết quả cũ khi lỗi."""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        dir=output_path.parent, suffix=".csv", delete=False
    ) as temporary:
        temp_path = Path(temporary.name)

    try:
        rfm.to_csv(
            temp_path, index_label="customer_unique_id", encoding="utf-8-sig"
        )
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)

    return output_path


def run_kmeans(
    connection, start_year, end_year,
    output_path="output/kmeans/customer_segments.csv",
):
    """Đọc DW, tính RFM, phân 4 cụm, gán tên và trả đường dẫn CSV."""
    orders = load_orders(connection, start_year, end_year)
    logger.info("Đã đọc %s đơn đã giao", len(orders))

    rfm = build_rfm(orders)
    scaled_features = scale_features(rfm)

    if len(np.unique(scaled_features, axis=0)) < 4:
        raise ValueError(
            "Cần ít nhất 4 hồ sơ RFM khác nhau để phân 4 cụm"
        )

    model = KMeans(n_clusters=4, random_state=42, n_init=10)
    rfm["kmeans_cluster"] = model.fit_predict(scaled_features)
    rfm["kmeans_segment"] = rfm["kmeans_cluster"].map(name_clusters(rfm))
    logger.info(
        "Phân bố nhóm:\n%s",
        rfm["kmeans_segment"].value_counts().to_string(),
    )

    saved_path = save_csv(rfm, output_path)
    logger.info("Đã lưu %s khách vào %s", len(rfm), saved_path)

    return saved_path


if __name__ == "__main__":
    from src.common.db import get_engine

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phân 4 cụm khách theo RFM")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()

    engine = get_engine()
    try:
        run_kmeans(engine, args.start_year, args.end_year)
    finally:
        engine.dispose()
